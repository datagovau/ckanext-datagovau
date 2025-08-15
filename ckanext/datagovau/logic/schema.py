import tempfile

from ckan import types
from ckan.logic.schema import validator_args


@validator_args
def extract_resource(
    not_missing: types.Validator,
    default: types.ValidatorFactory,
    unicode_safe: types.Validator,
) -> types.Schema:
    return {
        "id": [not_missing, unicode_safe],
        "tmp_dir": [default(tempfile.gettempdir()), unicode_safe],
    }


@validator_args
def suggest_dataset(
    not_empty: types.Validator,
    unicode_safe: types.Validator,
    email_validator: types.Validator,
) -> types.Schema:
    return {
        "content": [not_empty, unicode_safe],
        "name": [not_empty, unicode_safe],
        "email": [not_empty, unicode_safe, email_validator],
    }


@validator_args
def ask_question(
    not_empty: types.Validator,
    unicode_safe: types.Validator,
    package_id_exists: types.Validator,
) -> types.Schema:
    schema = suggest_dataset()

    schema["package_id"] = [not_empty, unicode_safe, package_id_exists]

    return schema
