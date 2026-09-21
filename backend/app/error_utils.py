from app.exceptions import BandAError
from app.schemas import ErrorDetail, ErrorResponse


def error_response_from_exception(exc: BandAError, correlation_id: str) -> dict:
    return ErrorResponse(
        error=ErrorDetail(
            code=exc.code,
            message=exc.message,
            run_created=exc.run_created,
            correlation_id=correlation_id,
            existing_run_id=getattr(exc, "existing_run_id", None),
        )
    ).model_dump()


def band_a_error_detail(exc: BandAError) -> dict:
    detail = {
        "code": exc.code,
        "message": exc.message,
        "run_created": exc.run_created,
    }
    if exc.existing_run_id:
        detail["existing_run_id"] = exc.existing_run_id
    return detail
