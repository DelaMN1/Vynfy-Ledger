from __future__ import annotations

from flask_wtf import FlaskForm
from wtforms import BooleanField, DecimalField, IntegerField, SelectField, StringField, SubmitField, TextAreaField
from wtforms.validators import DataRequired, Length, NumberRange, Optional

from app.utils.enums import AccountType, CategoryType, TransactionType, choices


class CategoryForm(FlaskForm):
    name = StringField("Name", validators=[DataRequired(), Length(max=120)])
    type = SelectField("Type", choices=choices(CategoryType), validators=[DataRequired()])
    color = StringField("Color", validators=[DataRequired(), Length(max=20)], default="#1d4ed8")
    description = TextAreaField("Description", validators=[Optional(), Length(max=500)])
    submit = SubmitField("Save category")


class AccountForm(FlaskForm):
    name = StringField("Name", validators=[DataRequired(), Length(max=120)])
    type = SelectField("Type", choices=choices(AccountType), validators=[DataRequired()])
    opening_balance = DecimalField("Opening balance", validators=[DataRequired(), NumberRange(min=0)], places=2)
    currency_code = StringField("Currency", validators=[DataRequired(), Length(max=10)], default="GHS")
    submit = SubmitField("Save account")


class PaymentMethodForm(FlaskForm):
    name = StringField("Name", validators=[DataRequired(), Length(max=80)])
    submit = SubmitField("Save payment method")


class BudgetForm(FlaskForm):
    name = StringField("Name", validators=[DataRequired(), Length(max=120)])
    transaction_type = SelectField("Type", validators=[Optional()], choices=[("", "All transactions")] + choices(TransactionType))
    category_id = SelectField("Category", coerce=int, validators=[Optional()], default=0, choices=[(0, "Any category")])
    account_id = SelectField("Account", coerce=int, validators=[Optional()], default=0, choices=[(0, "Any account")])
    owner_id = SelectField("Budget owner", coerce=int, validators=[Optional()], default=0, choices=[(0, "Unassigned")])
    amount = DecimalField("Monthly budget", validators=[DataRequired(), NumberRange(min=0.01)], places=2)
    alert_percent = IntegerField("Alert at %", validators=[DataRequired(), NumberRange(min=1, max=100)], default=80)
    submit = SubmitField("Save budget")


class SpendPolicyForm(FlaskForm):
    name = StringField("Name", validators=[DataRequired(), Length(max=120)])
    transaction_type = SelectField("Type", validators=[Optional()], choices=[("", "All transactions")] + choices(TransactionType))
    category_id = SelectField("Category", coerce=int, validators=[Optional()], default=0, choices=[(0, "Any category")])
    account_id = SelectField("Account", coerce=int, validators=[Optional()], default=0, choices=[(0, "Any account")])
    payment_method_id = SelectField("Payment method", coerce=int, validators=[Optional()], default=0, choices=[(0, "Any payment method")])
    max_amount = DecimalField("Max amount", validators=[Optional(), NumberRange(min=0.01)], places=2)
    require_attachment = BooleanField("Require attachment")
    require_note = BooleanField("Require note")
    block_on_over_budget = BooleanField("Block when over budget")
    description = TextAreaField("Description", validators=[Optional(), Length(max=500)])
    submit = SubmitField("Save policy")


class AccountingMappingForm(FlaskForm):
    name = StringField("Name", validators=[DataRequired(), Length(max=120)])
    transaction_type = SelectField("Type", validators=[Optional()], choices=[("", "All transactions")] + choices(TransactionType))
    category_id = SelectField("Category", coerce=int, validators=[Optional()], default=0, choices=[(0, "Any category")])
    account_id = SelectField("Account", coerce=int, validators=[Optional()], default=0, choices=[(0, "Any account")])
    payment_method_id = SelectField("Payment method", coerce=int, validators=[Optional()], default=0, choices=[(0, "Any payment method")])
    gl_code = StringField("GL code", validators=[DataRequired(), Length(max=50)])
    cost_center = StringField("Cost center", validators=[Optional(), Length(max=50)])
    project_code = StringField("Project code", validators=[Optional(), Length(max=50)])
    submit = SubmitField("Save mapping")
