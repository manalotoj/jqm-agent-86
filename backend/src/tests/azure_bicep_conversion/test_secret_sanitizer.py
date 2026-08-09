from agent_86.services.azure_bicep_conversion.secret_sanitizer import sanitize_bicep_secrets


def test_sanitize_bicep_secrets_clears_plaintext_defaults_for_secure_params() -> None:
    bicep_text = """
@secure()
param adminPassword string = 'SuperSecret!'

param location string = 'eastus'
""".strip()

    result = sanitize_bicep_secrets(bicep_text=bicep_text)

    assert "param adminPassword string = ''" in result.bicep_text
    assert "param location string = 'eastus'" in result.bicep_text
    assert result.secure_parameter_count == 1


def test_sanitize_bicep_secrets_leaves_non_secure_params_unchanged() -> None:
    bicep_text = "param location string = 'eastus'"

    result = sanitize_bicep_secrets(bicep_text=bicep_text)

    assert result.bicep_text == bicep_text
    assert result.secure_parameter_count == 0