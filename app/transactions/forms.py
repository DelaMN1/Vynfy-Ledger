from __future__ import annotations

from flask_wtf import FlaskForm
from flask_wtf.file import MultipleFileField
from wtforms import BooleanField, DateField, DecimalField, HiddenField, SelectField, StringField, SubmitField, TextAreaField
from wtforms.validators import DataRequired, Length, NumberRange, Optional

from app.utils.enums import ExpenseStatus, RevenueStatus, choices


class BaseTransactionForm(FlaskForm):
    title = StringField("Title", validators=[DataRequired(), Length(max=160)])
    description = TextAreaField("Description", validators=[Optional(), Length(max=2000)])
    counterparty = StringField("Counterparty", validators=[Optional(), Length(max=160)])
    category_id = SelectField("Category", coerce=int, validators=[DataRequired()])
    account_id = SelectField("Account", coerce=int, validators=[DataRequired()])
    payment_method_id = SelectField("Payment method", coerce=int, validators=[Optional()], default=0)
    transaction_date = DateField("Transaction date", validators=[DataRequired()])
    due_date = DateField("Due date", validators=[Optional()])
    settled_date = DateField("Settled date", validators=[Optional()])
    reference_number = StringField("Reference number", validators=[Optional(), Length(max=100)])
    note = TextAreaField("Notes", validators=[Optional(), Length(max=2000)])
    attachments = MultipleFileField("Attachments")
    save_draft = SubmitField("Save Draft")
    submit_record = SubmitField("Submit")


class RevenueForm(BaseTransactionForm):
    expected_amount = DecimalField("Expected amount", validators=[DataRequired(), NumberRange(min=0.01)], places=2)
    received_amount = DecimalField("Received amount", validators=[Optional(), NumberRange(min=0)], places=2)
    status = SelectField("Status", choices=choices(RevenueStatus), validators=[Optional()])


class ExpenseForm(BaseTransactionForm):
    amount = DecimalField("Amount", validators=[DataRequired(), NumberRange(min=0.01)], places=2)
    reimbursable = BooleanField("Reimbursable")
    status = SelectField("Status", choices=choices(ExpenseStatus), validators=[Optional()])


class ExpenseActionForm(FlaskForm):
    note = TextAreaField("Note", validators=[Optional(), Length(max=1000)])
    submit = SubmitField("Save")


class SettlementForm(FlaskForm):
    amount = DecimalField("Amount", validators=[Optional(), NumberRange(min=0)], places=2)
    settled_date = DateField("Settlement date", validators=[Optional()])
    submit = SubmitField("Confirm")


class DeleteDraftForm(FlaskForm):
    submit = SubmitField("Delete draft")


class TransactionCommentForm(FlaskForm):
    body = TextAreaField("Comment", validators=[DataRequired(), Length(max=1000)])
    submit = SubmitField("Post comment")


class TransactionFilterForm(FlaskForm):
    q = StringField("Search", validators=[Optional(), Length(max=120)])
    status = SelectField("Status", validators=[Optional()], choices=[("", "All statuses")])
    category_id = SelectField("Category", validators=[Optional()], coerce=int, default=0)
    account_id = SelectField("Account", validators=[Optional()], coerce=int, default=0)
    owner_id = SelectField("Owner", validators=[Optional()], coerce=int, default=0)
    start_date = DateField("From", validators=[Optional()])
    end_date = DateField("To", validators=[Optional()])
    transaction_type = HiddenField()
