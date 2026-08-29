"""V8: Agent Runtime with durable checkpoint recovery.

V7 made progress visible. V8 persists that progress and demonstrates a safe
resume boundary: crash only after an Observation has been recorded. A fresh
Runtime can reload AgentState and continue by sending the saved Observation
back to the Model instead of re-running the completed Tool.

Checkpointing is not exactly-once execution. A crash after an external side
effect but before its post-effect checkpoint can still create ambiguity.
"""

import json

from context import ExecutionContext, default_execution_context
from model_validation import validate_model_response
from policy import DEFAULT_POLICY, PolicyDecision
from state import AgentState, InMemoryStateStore, StateStore
from tools import TOOL_REGISTRY, Tool, calculator, resolve_tool


DEFAULT_MAX_STEPS = 5

tool_registry = TOOL_REGISTRY


class SimulatedCrash(RuntimeError):
    """Teaching-only exception used to imitate sudden process death."""


def _emit(on_event, event_type: str, **payload) -> None:
    if on_event is not None:
        on_event({"type": event_type, **payload})


def _save_state(
    state_store: StateStore,
    state: AgentState,
    on_event,
    *,
    reason: str,
) -> None:
    state_store.save(state, reason=reason)
    _emit(
        on_event,
        "state_saved",
        reason=reason,
        store=state_store.__class__.__name__,
        state=state.to_dict(),
    )


def _tool_call_key(tool_name: str, arguments: dict) -> str:
    normalized_arguments = json.dumps(
        arguments,
        sort_keys=True,
        separators=(",", ":"),
        default=str,
    )
    return f"{tool_name}:{normalized_arguments}"


def _execution_error(tool_name: str, exc: Exception) -> dict:
    return {
        "error": {
            "code": "tool_execution_error",
            "message": f"{tool_name} failed: {exc}",
        }
    }


def _execute_tool_with_retry(
    *,
    tool: Tool,
    arguments: dict,
    on_event=None,
    max_retries_override: int | None = None,
):
    max_retries = tool.max_retries if max_retries_override is None else max_retries_override
    total_attempts = max_retries + 1

    for attempt in range(1, total_attempts + 1):
        _emit(
            on_event,
            "tool_attempt",
            tool_name=tool.name,
            arguments=arguments,
            attempt=attempt,
            total_attempts=total_attempts,
            retry_policy={
                "max_retries": max_retries,
                "retryable_errors": [error.__name__ for error in tool.retryable_errors],
            },
        )

        try:
            result = tool.function(**arguments)
        except tool.retryable_errors as exc:
            if attempt < total_attempts:
                _emit(
                    on_event,
                    "tool_retry",
                    tool_name=tool.name,
                    attempt=attempt,
                    next_attempt=attempt + 1,
                    error_type=exc.__class__.__name__,
                    error=str(exc),
                    policy_source="Tool.max_retries",
                )
                continue

            error = {
                "code": "tool_retry_exhausted",
                "message": (
                    f"{tool.name} still failed after {total_attempts} "
                    f"attempt(s): {exc}"
                ),
            }
            _emit(
                on_event,
                "tool_error",
                tool_name=tool.name,
                retryable=True,
                attempts=attempt,
                error=error,
            )
            return {"error": error}
        except Exception as exc:
            observation = _execution_error(tool.name, exc)
            _emit(
                on_event,
                "tool_error",
                tool_name=tool.name,
                retryable=False,
                attempts=attempt,
                error=observation["error"],
            )
            return observation
        else:
            _emit(
                on_event,
                "tool_result",
                tool_name=tool.name,
                result=result,
                attempts=attempt,
            )
            return result

    raise AssertionError("retry loop exited unexpectedly")


def _stop_agent(
    on_event,
    error: dict,
    *,
    reason: str,
    state: AgentState,
    state_store: StateStore,
) -> str:
    content = f"Agent stopped [{error['code']}]: {error['message']}"
    state.status = "stopped"
    state.phase = "stopped"
    state.stop_reason = reason
    state.final_answer = content
    _save_state(state_store, state, on_event, reason="runtime_stopped")

    _emit(
        on_event,
        "runtime_stop",
        reason=reason,
        error=error,
        step=state.step,
        max_steps=state.max_steps,
    )
    _emit(on_event, "final", content=content, stopped=True)
    return content


def _policy_observation(decision: PolicyDecision, reason: str) -> dict:
    if decision is PolicyDecision.REQUIRE_APPROVAL:
        return {
            "error": {
                "code": "approval_required",
                "message": reason,
            }
        }

    return {
        "error": {
            "code": "policy_denied",
            "message": reason,
        }
    }


def _resume_from_observation_checkpoint(
    *,
    model,
    state: AgentState,
    state_store: StateStore,
    on_event,
):
    """Continue after a Tool Observation was durably saved.

    The completed Tool is not executed again. Runtime reloads the Observation
    and model-continuation identifiers that were persisted with AgentState.
    """
    if state.phase != "observation_ready":
        raise RuntimeError(
            "V8 can resume only from an observation_ready checkpoint; "
            f"found phase={state.phase!r}."
        )
    if not state.current_tool or not state.pending_response_id or not state.pending_call_id:
        raise RuntimeError("Checkpoint is missing model continuation metadata")

    completed_tool = state.current_tool
    saved_observation = state.last_observation

    _emit(
        on_event,
        "checkpoint_loaded",
        store=state_store.__class__.__name__,
        resume_from="observation_ready",
        state=state.to_dict(),
    )
    _emit(
        on_event,
        "resume_boundary",
        message="Observation already checkpointed; skip completed Tool execution.",
        tool_name=completed_tool,
        observation=saved_observation,
    )

    state.phase = "model_thinking"
    state.current_tool = None
    state.current_arguments = None
    _save_state(state_store, state, on_event, reason="resume_model_continuation")

    _emit(
        on_event,
        "model_request",
        phase="resume",
        previous_response_id=state.pending_response_id,
        call_id=state.pending_call_id,
        tool_name=completed_tool,
        result=saved_observation,
    )
    response = model.continue_with_tool_result(
        previous_response_id=state.pending_response_id,
        call_id=state.pending_call_id,
        tool_name=completed_tool,
        result=saved_observation,
    )
    _emit(on_event, "model_response", response=response)
    return response


def run_agent(
    user_message: str,
    model=None,
    on_event=None,
    max_steps: int = DEFAULT_MAX_STEPS,
    max_retries: int | None = None,
    policy=None,
    execution_context: ExecutionContext | None = None,
    state_store: StateStore | None = None,
    resume: bool = False,
    crash_after_observations: int | None = None,
) -> str:
    """Run or resume the Agent Loop.

    V8 recovery contract:
    - normal run: create a new AgentState and checkpoint transitions;
    - simulated crash: raise only after an Observation has been saved;
    - resume: load that observation_ready state and continue Model reasoning;
    - already completed Tool execution is not repeated.
    """
    if not isinstance(max_steps, int) or isinstance(max_steps, bool) or max_steps < 1:
        raise ValueError("max_steps must be a positive integer")
    if max_retries is not None and (
        not isinstance(max_retries, int)
        or isinstance(max_retries, bool)
        or max_retries < 0
    ):
        raise ValueError("max_retries must be None or a non-negative integer")
    if crash_after_observations is not None and (
        not isinstance(crash_after_observations, int)
        or isinstance(crash_after_observations, bool)
        or crash_after_observations < 1
    ):
        raise ValueError("crash_after_observations must be None or a positive integer")

    if model is None:
        from model_adapters import FakeModel
        model = FakeModel()

    runtime_context = (
        default_execution_context() if execution_context is None else execution_context
    )
    if not isinstance(runtime_context, ExecutionContext):
        raise TypeError("execution_context must be an ExecutionContext")

    runtime_store = InMemoryStateStore() if state_store is None else state_store
    if not isinstance(runtime_store, StateStore):
        raise TypeError("state_store must implement StateStore")

    policy_engine = DEFAULT_POLICY if policy is None else policy

    _emit(
        on_event,
        "execution_context",
        context=runtime_context.to_dict(),
        source="Runtime re-injected" if resume else "Runtime injected",
    )

    if resume:
        state = runtime_store.load(runtime_context.task_id)
        if state is None:
            raise RuntimeError(f"No checkpoint found for task_id={runtime_context.task_id}")
        if state.status == "completed":
            _emit(
                on_event,
                "checkpoint_loaded",
                store=runtime_store.__class__.__name__,
                resume_from="completed",
                state=state.to_dict(),
            )
            _emit(on_event, "final", content=state.final_answer, stopped=False, resumed=True)
            return state.final_answer or ""
        if state.status != "running":
            raise RuntimeError(f"Checkpoint is not resumable: status={state.status}")

        max_steps = state.max_steps
        seen_calls = set(state.seen_calls)
        response = _resume_from_observation_checkpoint(
            model=model,
            state=state,
            state_store=runtime_store,
            on_event=on_event,
        )
    else:
        seen_calls: set[str] = set()
        state = AgentState(task_id=runtime_context.task_id, max_steps=max_steps)

        state.phase = "received_input"
        _save_state(runtime_store, state, on_event, reason="runtime_started")
        _emit(on_event, "user_input", message=user_message)

        state.phase = "model_thinking"
        _save_state(runtime_store, state, on_event, reason="model_requested")
        _emit(on_event, "model_request", phase="start", message=user_message)
        response = model.start(user_message)
        _emit(on_event, "model_response", response=response)

    while True:
        response_validation = validate_model_response(response)
        _emit(
            on_event,
            "model_validation",
            response=response,
            validation=response_validation,
        )

        if not response_validation["ok"]:
            return _stop_agent(
                on_event,
                response_validation["error"],
                reason="invalid_model_response",
                state=state,
                state_store=runtime_store,
            )

        if response["type"] == "final":
            state.status = "completed"
            state.phase = "completed"
            state.current_tool = None
            state.current_arguments = None
            state.final_answer = response["content"]
            _save_state(runtime_store, state, on_event, reason="final_answer")
            _emit(on_event, "final", content=response["content"], stopped=False)
            return response["content"]

        if state.step >= max_steps:
            error = {
                "code": "max_steps_exceeded",
                "message": (
                    f"Runtime refused another Tool Call after {max_steps} "
                    "allowed step(s)."
                ),
            }
            return _stop_agent(
                on_event,
                error,
                reason="max_steps",
                state=state,
                state_store=runtime_store,
            )

        state.step += 1
        tool_name = response["tool_name"]
        arguments = response["arguments"]
        state.phase = "tool_selected"
        state.current_tool = tool_name
        state.current_arguments = dict(arguments)
        state.pending_response_id = response.get("response_id")
        state.pending_call_id = response.get("call_id")
        _save_state(runtime_store, state, on_event, reason="tool_selected")

        _emit(
            on_event,
            "runtime_step",
            step=state.step,
            max_steps=max_steps,
            tool_name=tool_name,
        )

        call_key = _tool_call_key(tool_name, arguments)
        is_duplicate = call_key in seen_calls
        _emit(
            on_event,
            "duplicate_check",
            tool_name=tool_name,
            arguments=arguments,
            call_key=call_key,
            duplicate=is_duplicate,
        )

        if is_duplicate:
            observation = {
                "error": {
                    "code": "duplicate_tool_call",
                    "message": (
                        "Runtime blocked an exact repeated Tool Call. "
                        "The model should use the existing Observation or choose a new action."
                    ),
                }
            }
            _emit(
                on_event,
                "tool_rejected",
                tool_name=tool_name,
                reason="duplicate_tool_call",
                error=observation["error"],
            )
        else:
            seen_calls.add(call_key)
            state.seen_calls = sorted(seen_calls)
            state.phase = "validating_tool"
            _save_state(runtime_store, state, on_event, reason="tool_validation_started")
            tool = resolve_tool(tool_name)

            _emit(
                on_event,
                "tool_lookup",
                tool_name=tool_name,
                found=tool is not None,
                registry_keys=list(tool_registry.keys()),
                tool_metadata=tool.trace_metadata() if tool is not None else None,
            )

            if tool is None:
                validation = {
                    "ok": False,
                    "error": {
                        "code": "unknown_tool",
                        "message": f"Unknown tool: {tool_name}",
                    },
                }
            else:
                validation = tool.validate(arguments)

            _emit(
                on_event,
                "tool_validation",
                tool_name=tool_name,
                arguments=arguments,
                validation=validation,
                validator_source="Tool.validate" if tool is not None else "Registry",
            )

            if not validation["ok"]:
                observation = {"error": validation["error"]}
                _emit(
                    on_event,
                    "tool_rejected",
                    tool_name=tool_name,
                    reason="validation",
                    error=validation["error"],
                )
            else:
                state.phase = "checking_policy"
                _save_state(runtime_store, state, on_event, reason="policy_check_started")
                policy_result = policy_engine.evaluate(
                    tool,
                    arguments,
                    runtime_context,
                )
                _emit(
                    on_event,
                    "policy_decision",
                    tool_name=tool.name,
                    arguments=arguments,
                    tool_risk=tool.risk,
                    context=runtime_context.to_dict(),
                    policy=policy_result.to_dict(),
                )

                if policy_result.decision is not PolicyDecision.ALLOW:
                    observation = _policy_observation(
                        policy_result.decision,
                        policy_result.reason,
                    )
                    _emit(
                        on_event,
                        "tool_rejected",
                        tool_name=tool.name,
                        reason=policy_result.decision.value,
                        error=observation["error"],
                    )
                else:
                    state.phase = "executing_tool"
                    _save_state(runtime_store, state, on_event, reason="tool_execution_started")
                    effective_retries = tool.max_retries if max_retries is None else max_retries
                    _emit(
                        on_event,
                        "tool_execute",
                        tool_name=tool.name,
                        arguments=arguments,
                        context=runtime_context.to_dict(),
                        tool_metadata=tool.trace_metadata(),
                        effective_max_retries=effective_retries,
                        retry_policy_source=(
                            "Tool.max_retries" if max_retries is None else "Runtime override"
                        ),
                    )
                    observation = _execute_tool_with_retry(
                        tool=tool,
                        arguments=arguments,
                        max_retries_override=max_retries,
                        on_event=on_event,
                    )

        state.phase = "observation_ready"
        state.record_observation(tool_name, observation)
        _save_state(runtime_store, state, on_event, reason="observation_recorded")
        _emit(
            on_event,
            "tool_observation",
            tool_name=tool_name,
            observation=observation,
        )

        if (
            crash_after_observations is not None
            and len(state.observations) >= crash_after_observations
        ):
            _emit(
                on_event,
                "simulated_crash",
                message="Process died after durable Observation checkpoint.",
                safe_resume_phase=state.phase,
                state=state.to_dict(),
            )
            raise SimulatedCrash(
                f"Simulated crash after {len(state.observations)} checkpointed observation(s)"
            )

        completed_tool = tool_name
        saved_response_id = state.pending_response_id
        saved_call_id = state.pending_call_id
        state.phase = "model_thinking"
        state.current_tool = None
        state.current_arguments = None
        _save_state(runtime_store, state, on_event, reason="model_continuation")
        _emit(
            on_event,
            "model_request",
            phase="continue",
            previous_response_id=saved_response_id,
            call_id=saved_call_id,
            tool_name=completed_tool,
            result=observation,
        )

        response = model.continue_with_tool_result(
            previous_response_id=saved_response_id,
            call_id=saved_call_id,
            tool_name=completed_tool,
            result=observation,
        )
        _emit(on_event, "model_response", response=response)


if __name__ == "__main__":
    answer = run_agent("Please calculate 10 + 20.")
    print(answer)
