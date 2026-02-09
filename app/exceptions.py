class AppError(Exception):
    def __init__(self, message, status_code=500):
        self.message = message
        self.status_code = status_code
        super().__init__(self.message)


class NotFoundError(AppError):
    def __init__(self, resource, resource_id):
        super().__init__(f"{resource} {resource_id} not found", status_code=404)


class ConflictError(AppError):
    def __init__(self, message):
        super().__init__(message, status_code=409)


class ValidationError(AppError):
    def __init__(self, message):
        super().__init__(message, status_code=422)


class AuthorizationError(AppError):
    def __init__(self, message="Insufficient permissions"):
        super().__init__(message, status_code=403)
