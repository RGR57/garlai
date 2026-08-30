from src.models.execution_state import ExecutionState


class ReviewerService:

    async def review(
        self,
        state: ExecutionState,
    ) -> tuple[bool, str]:

        last = state.last_result()

        if last is None:
            return False, "Execution produced no result."

        if not last.success:
            return False, last.error or "Execution failed."

        if last.output is None:
            return False, "Execution returned no output."

        return True, str(last.output)