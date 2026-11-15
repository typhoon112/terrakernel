from terrakernel.extract import _parse_value
from terrakernel.extract.schemas import Attribute


def test_unknown_attribute_remains_unknown_with_string_schema():
    attribute = Attribute.model_validate({"key": "unit", "value": None})
    assert _parse_value(attribute.value) is None
    assert Attribute.model_json_schema()["properties"]["value"]["type"] == "string"
