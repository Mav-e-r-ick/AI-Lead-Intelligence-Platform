"""The canonical field-name vocabulary every cleaning rule is written against.

WHY THIS FILE EXISTS:
Every rule below is described in CLEANING_RULES.md against the reference
dataset's literal column headers ("Email", "Direct Phone", ...). But the
Import Engine was explicitly built so a future source can use completely
different headers ("E-mail Address" instead of "Email") — if rules were
hardwired to today's literal strings, that portability would break the
moment cleaning started.

The fix: rules read and write **canonical field names** (plain strings
below, e.g. `EMAIL`), never literal source headers. A CleaningProfile
carries an explicit `field_mapping: canonical name -> source column name`
for whatever dataset it's cleaning. CleaningPipeline translates a
RawRecord's literal-keyed values into canonical-keyed values using that
mapping before any rule ever runs, and translates back afterward.

DEFAULT_FIELD_MAPPING below is the mapping for the one schema we have real
evidence about (the D&B Hoovers export profiled during the Import Engine
task) — provided as a working default, not as a hardcoded assumption that
every future file will look like this one.
"""

from __future__ import annotations

# --- Identity ---------------------------------------------------------
FIRST_NAME = "first_name"
LAST_NAME = "last_name"
TITLE = "title"
CONTACT_LEVEL = "contact_level"
JOB_FUNCTION = "job_function"

# --- Contact ------------------------------------------------------------
EMAIL = "email"
COMPANY_EMAIL = "company_email"
EMAIL_USAGE_RESTRICTION = "email_usage_restriction"
DIRECT_PHONE = "direct_phone"
DIRECT_PHONE_USAGE_RESTRICTION = "direct_phone_usage_restriction"
PHONE = "phone"
FAX = "fax"

# --- Company --------------------------------------------------------------
COMPANY_NAME = "company_name"
TRADESTYLE = "tradestyle"
OWNERSHIP_TYPE = "ownership_type"
LEGAL_STATUS_TYPE = "legal_status_type"
ENTITY_TYPE = "entity_type"
IS_HEADQUARTERS = "is_headquarters"
TICKER = "ticker"
PARENT_COMPANY = "parent_company"
PARENT_COUNTRY = "parent_country"
GLOBAL_ULTIMATE_COMPANY = "global_ultimate_company"
GLOBAL_ULTIMATE_COUNTRY = "global_ultimate_country"
BUSINESS_DESCRIPTION = "business_description"
DUNS_NUMBER = "duns_number"
KEY_ID = "key_id"

# --- Address -------------------------------------------------------------
ADDRESS_LINE_1 = "address_line_1"
ADDRESS_LINE_2 = "address_line_2"
ADDRESS_LINE_3 = "address_line_3"
CITY = "city"
STATE_OR_PROVINCE = "state_or_province"
POSTAL_CODE = "postal_code"
COUNTRY = "country"

# --- Financial -----------------------------------------------------------
SALES_USD = "sales_usd"
PRE_TAX_PROFIT_USD = "pre_tax_profit_usd"
ASSETS_USD = "assets_usd"
LIABILITIES_USD = "liabilities_usd"
EMPLOYEES_SINGLE_SITE = "employees_single_site"
EMPLOYEES_TOTAL = "employees_total"

# --- Industry --------------------------------------------------------
INDUSTRY_LABEL = "industry_label"
US_SIC8_CODE = "us_sic8_code"
US_SIC8_DESC = "us_sic8_description"
US_SIC1987_CODE = "us_sic1987_code"
US_SIC1987_DESC = "us_sic1987_description"
NAICS_CODE = "naics_code"
NAICS_DESC = "naics_description"
UK_SIC_CODE = "uk_sic_code"
UK_SIC_DESC = "uk_sic_description"
ISIC_CODE = "isic_code"
ISIC_DESC = "isic_description"
NACE_CODE = "nace_code"
NACE_DESC = "nace_description"
ANZSIC_CODE = "anzsic_code"
ANZSIC_DESC = "anzsic_description"

CLASSIFICATION_CODE_DESCRIPTION_PAIRS: tuple[tuple[str, str], ...] = (
    (US_SIC8_CODE, US_SIC8_DESC),
    (US_SIC1987_CODE, US_SIC1987_DESC),
    (NAICS_CODE, NAICS_DESC),
    (UK_SIC_CODE, UK_SIC_DESC),
    (ISIC_CODE, ISIC_DESC),
    (NACE_CODE, NACE_DESC),
    (ANZSIC_CODE, ANZSIC_DESC),
)

# --- Metadata --------------------------------------------------------
SOURCE = "source"
TPS_FLAG = "tps_flag"
DIRECT_MARKETING_STATUS = "direct_marketing_status"
URL = "url"
DEDUP_ID = "dedup_id"

# Derived attributes some rules produce in addition to source fields
COMPANY_NAME_NORMALIZED = "company_name_normalized"
PRIMARY_EMAIL = "primary_email"
PRIMARY_PHONE = "primary_phone"
NAME_SUFFIX = "name_suffix"

#: canonical field name -> literal source column header, for the reference
#: D&B Hoovers export profiled during the Import Engine task.
DEFAULT_FIELD_MAPPING: dict[str, str] = {
    FIRST_NAME: "First Name",
    LAST_NAME: "Last Name",
    TITLE: "Title",
    CONTACT_LEVEL: "Contact Level",
    JOB_FUNCTION: "Job Function",
    EMAIL: "Email",
    COMPANY_EMAIL: "Company Email",
    EMAIL_USAGE_RESTRICTION: "Email usage restriction",
    DIRECT_PHONE: "Direct Phone",
    DIRECT_PHONE_USAGE_RESTRICTION: "Direct phone usage restriction",
    PHONE: "Phone",
    FAX: "Fax",
    COMPANY_NAME: "Company Name",
    TRADESTYLE: "Tradestyle",
    OWNERSHIP_TYPE: "Ownership Type",
    LEGAL_STATUS_TYPE: "D&B Legal Status Type",
    ENTITY_TYPE: "Entity Type",
    IS_HEADQUARTERS: "Is Headquarters",
    TICKER: "Ticker",
    PARENT_COMPANY: "Parent Company",
    PARENT_COUNTRY: "Parent Country/Region",
    GLOBAL_ULTIMATE_COMPANY: "Global Ultimate Company",
    GLOBAL_ULTIMATE_COUNTRY: "Global Ultimate Country/Region",
    BUSINESS_DESCRIPTION: "Business Description",
    DUNS_NUMBER: "D-U-N-S® Number",
    KEY_ID: "Key ID",
    ADDRESS_LINE_1: "Address Line 1",
    ADDRESS_LINE_2: "Address Line 2",
    ADDRESS_LINE_3: "Address Line 3",
    CITY: "City",
    STATE_OR_PROVINCE: "State Or Province",
    POSTAL_CODE: "Postal Code",
    COUNTRY: "Country/Region",
    SALES_USD: "Sales (USD)",
    PRE_TAX_PROFIT_USD: "Pre Tax Profit (USD)",
    ASSETS_USD: "Assets (USD)",
    LIABILITIES_USD: "Liabilities (USD)",
    EMPLOYEES_SINGLE_SITE: "Employees (Single Site)",
    EMPLOYEES_TOTAL: "Employees (Total)",
    INDUSTRY_LABEL: "D&B Hoovers Industry",
    US_SIC8_CODE: "US 8-Digit SIC Code",
    US_SIC8_DESC: "US 8-Digit SIC Description",
    US_SIC1987_CODE: "US SIC 1987 Code",
    US_SIC1987_DESC: "US SIC 1987 Description",
    NAICS_CODE: "NAICS 2022 Code",
    NAICS_DESC: "NAICS 2022 Description",
    UK_SIC_CODE: "UK SIC 2007 Code",
    UK_SIC_DESC: "UK SIC 2007 Description",
    ISIC_CODE: "ISIC Rev 4 Code",
    ISIC_DESC: "ISIC Rev 4 Description",
    NACE_CODE: "NACE Rev 2 Code",
    NACE_DESC: "NACE Rev 2 Description",
    ANZSIC_CODE: "ANZSIC 2006 Code",
    ANZSIC_DESC: "ANZSIC 2006 Description",
    SOURCE: "Source",
    TPS_FLAG: "TPS Flag",
    DIRECT_MARKETING_STATUS: "Direct Marketing Status",
    URL: "URL",
    DEDUP_ID: "Dedup ID",
}
