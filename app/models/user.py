# app/models/user.py
# Note: User is already defined in core/auth.py, so we do not redefine it here.
# If you want to add more fields, do so in core/auth.py or import it here.

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from .category import Category
    from .expense import Expense
    from .transaction import Transaction
    from .goal import Goal

# (All additional fields handled in core/auth.py)
