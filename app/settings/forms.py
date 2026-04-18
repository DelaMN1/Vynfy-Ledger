from __future__ import annotations

from flask_wtf import FlaskForm
from wtforms import DecimalField, SelectField, StringField, SubmitField, TextAreaField
from wtforms.validators import DataRequired, Length, NumberRange, Optional

from app.utils.enums import AccountType, CategoryType, choices


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
