INSERT INTO calaccess_processed_schedulegitem (
    filing_id,
    line_item,
    agent_title,
    agent_lastname,
    agent_firstname,
    agent_name_suffix,
    payee_code,
    payee_committee_id,
    payee_title,
    payee_lastname,
    payee_firstname,
    payee_name_suffix,
    payee_city,
    payee_state,
    payee_zip,
    treasurer_title,
    treasurer_lastname,
    treasurer_firstname,
    treasurer_name_suffix,
    treasurer_city,
    treasurer_state,
    treasurer_zip,
    payment_code,
    payment_description,
    amount,
    expense_date,
    check_number,
    transaction_id,
    parent_transaction_id,
    parent_schedule,
    memo_reference_number
)
SELECT 
    filing_version.filing_id,
    items.line_item,
    items.agent_title,
    items.agent_lastname,
    items.agent_firstname,
    items.agent_name_suffix,
    items.payee_code,
    items.payee_committee_id,
    items.payee_title,
    items.payee_lastname,
    items.payee_firstname,
    items.payee_name_suffix,
    items.payee_city,
    items.payee_state,
    items.payee_zip,
    items.treasurer_title,
    items.treasurer_lastname,
    items.treasurer_firstname,
    items.treasurer_name_suffix,
    items.treasurer_city,
    items.treasurer_state,
    items.treasurer_zip,
    items.payment_code,
    items.payment_description,
    items.amount,
    items.expense_date,
    items.check_number,
    items.transaction_id,
    items.parent_transaction_id,
    items.parent_schedule,
    items.memo_reference_number
FROM calaccess_processed_form460 filing
JOIN calaccess_processed_form460version filing_version
ON filing.filing_id = filing_version.filing_id
AND filing.amendment_count = filing_version.amend_id
JOIN calaccess_processed_schedulegitemversion items
ON filing_version.id = items.filing_version_id;