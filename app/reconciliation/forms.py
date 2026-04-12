from __future__ import annotations

from flask_wtf import FlaskForm
from wtforms import DateField, DecimalField, SelectField, SubmitField, TextAreaField
from wtforms.validators import DataRequired, NumberRange, Optional


class ReconciliationForm(FlaskForm):
    account_id = SelectField("Account", coerce=int, validators=[DataRequired()])
    period_start = DateField("Period start", validators=[DataRequired()])
    period_end = DateField("Period end", validators=[DataRequired()])
    statement_ending_balance = DecimalField("Statement ending balance", validators=[DataRequired(), NumberRange(min=0)], places=2)
    notes = TextAreaField("Notes", validators=[Optional()])
    submit = SubmitField("Start reconciliation")
