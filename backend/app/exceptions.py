class BandAError(Exception):
    def __init__(
        self,
        code: str,
        message: str,
        run_created: bool = False,
        status_code: int = 400,
        existing_run_id: str | None = None,
    ):
        self.code = code
        self.message = message
        self.run_created = run_created
        self.status_code = status_code
        self.existing_run_id = existing_run_id
        super().__init__(message)


class AuthenticationError(BandAError):
    def __init__(self, message: str = "Authentication failed"):
        super().__init__("AUTHENTICATION_FAILED", message, run_created=False, status_code=401)


class TenantMismatchError(BandAError):
    def __init__(self, message: str):
        super().__init__("TENANT_MISMATCH", message, run_created=False, status_code=403)


class BudgetExceededError(BandAError):
    def __init__(self, message: str):
        super().__init__("BUDGET_EXCEEDED", message, run_created=False, status_code=429)


class ValidationError(BandAError):
    def __init__(self, message: str):
        super().__init__("VALIDATION_ERROR", message, run_created=False, status_code=422)


class SignatureError(BandAError):
    def __init__(self, message: str = "Invalid webhook signature"):
        super().__init__("SIGNATURE_INVALID", message, run_created=False, status_code=401)


class ActiveRunExistsError(BandAError):
    def __init__(self, message: str, existing_run_id: str):
        super().__init__(
            "ACTIVE_RUN_EXISTS",
            message,
            run_created=False,
            status_code=409,
            existing_run_id=existing_run_id,
        )
