from src.models.artifact import Artifact
from src.models.chat_response import ChatResponse
from src.models.execution_state import ExecutionState


class ResponseComposer:

    async def compose(
        self,
        execution_state: ExecutionState,
    ) -> ChatResponse:

        artifacts = [
            result.artifact
            for result in execution_state.history
            if result.artifact is not None
        ]

        last = execution_state.last_result()

        if last is None:

            return ChatResponse(
                response="Execution completed.",
                artifacts=[],
            )

        if not last.success:

            return ChatResponse(
                response=last.error
                or "Execution failed.",
                artifacts=artifacts,
            )

        return ChatResponse(
            response=self._build_response(
                execution_state,
                artifacts,
            ),
            artifacts=artifacts,
        )
    def _build_response(
        self,
        execution_state: ExecutionState,
        artifacts: list[Artifact],
    ) -> str:

        lines: list[str] = []

        lines.append("Done.")

        if artifacts:

            lines.append("")

            if len(artifacts) == 1:

                artifact = artifacts[0]

                lines.append(
                    f"I created **{artifact.name}**."
                )

                if artifact.preview:

                    lines.extend(
                        [
                            "",
                            "Preview:",
                            "",
                            artifact.preview,
                        ]
                    )

            else:

                lines.append(
                    f"I created {len(artifacts)} artifacts."
                )

                for artifact in artifacts:

                    lines.append(
                        f"- {artifact.name}"
                    )

        last = execution_state.last_result()

        if (
            last is not None
            and last.output
            and not artifacts
        ):

            lines.extend(
                [
                    "",
                    str(last.output),
                ]
            )

        return "\n".join(lines)

    def _summarize_artifact(
        self,
        artifact: Artifact,
    ) -> str:

        if artifact.artifact_type.value == "python":
            return "Python source file"

        if artifact.artifact_type.value == "json":
            return "JSON document"

        if artifact.artifact_type.value == "csv":
            return "CSV dataset"

        if artifact.artifact_type.value == "markdown":
            return "Markdown document"

        if artifact.artifact_type.value == "pdf":
            return "PDF document"

        if artifact.artifact_type.value == "image":
            return "Image"

        return "Generated artifact"
