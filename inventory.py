class InventoryError(Exception):
    pass

def validate_name(value: str, field: str = "Name") -> str:
    value = value.strip()
    if not value:
        raise InventoryError(f"{field} cannot be empty.")
    if len(value) > 80:
        raise InventoryError(f"{field} must be 80 characters or fewer.")
    return value

def validate_category(value: str) -> str:
    return validate_name(value, "Category")

def validate_quantity(value: int) -> int:
    if value <= 0:
        raise InventoryError("Quantity must be greater than 0.")
    return value

def validate_price(value: float) -> float:
    if value < 0:
        raise InventoryError("Price cannot be negative.")
    return round(float(value), 2)
