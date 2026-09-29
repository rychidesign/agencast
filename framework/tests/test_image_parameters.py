"""Image parameters: templates, quality precedence and model constraints (0.14.0)."""
import httpx
import pytest
import yaml
from conftest import add_image_model, events, run, scenario

from agencast import ConfigErrors
from agencast.fake import Fake
from agencast.loader import scenario_schema_errors
from agencast.validate import validate


def image_scenario(wf, params, inputs=None, model="gpt-image"):
    return scenario(wf, yaml.safe_dump({
        "version": 1, "name": "test", "description": "Image parameters",
        "inputs": inputs or {},
        "steps": [{"id": "photo", "image": {"model": model, "prompt": "Coffee", **params}}],
    }))


def test_image_templates_and_quality_override(wf):
    add_image_model(wf, quality="low")
    path = image_scenario(wf, {"aspect_ratio": "{{ inputs.aspect_ratio }}", "quality": "{{ inputs.quality }}",
                              "resolution": "{{ inputs.resolution }}"}, {
        "aspect_ratio": {"type": "string", "default": "3:2"},
        "quality": {"type": "string", "default": "high"},
        "resolution": {"type": "string", "default": "2K"},
    })
    result, fake = run(path)
    assert result.status == "succeeded", result.error
    body = fake.calls[0][2]
    assert body == {"model": "openai/gpt-image-2", "prompt": "Coffee", "aspect_ratio": "3:2",
                    "quality": "high", "resolution": "2K"}
    saved = events(result, "image_saved")[0]
    assert saved["width"] / saved["height"] == 1.5
    prompt = (result.rec.dir / "steps/01-photo/prompt.md").read_text()
    assert "aspect_ratio: 3:2" in prompt and "quality: high" in prompt and "resolution: 2K" in prompt


@pytest.mark.parametrize("field,value", [("aspect_ratio", "0:5"), ("quality", "ultra"), ("resolution", "8K")])
def test_invalid_rendered_parameter_is_config(wf, field, value):
    add_image_model(wf)
    path = image_scenario(wf, {field: "{{ inputs.x }}"}, {"x": {"type": "string", "required": True}})
    result, fake = run(path, {"x": value})
    assert result.error["class"] == "config" and value in result.error["message"]
    assert not fake.calls


def test_chat_warns_and_omits_parameters(wf):
    path = image_scenario(wf, {"aspect_ratio": "{{ inputs.aspect_ratio }}", "quality": "high", "resolution": "1K"},
                          {"aspect_ratio": {"type": "string", "default": "4:5"}}, model="gemini-image")
    result, fake = run(path)
    assert result.status == "succeeded", result.error
    assert fake.calls[0][2]["image_config"] == {"aspect_ratio": "4:5"}
    assert "quality" not in fake.calls[0][2] and "resolution" not in fake.calls[0][2]
    warning = "model using the chat API ignores quality/resolution"
    assert any(warning in text for text in events(result, "run_finished")[0]["warnings"])
    assert warning in (result.rec.dir / "summary.md").read_text()


@pytest.mark.parametrize("field,value", [("quality", "high"), ("resolution", "4K"), ("aspect_ratio", "5:4")])
@pytest.mark.parametrize("templated", [False, True])
def test_model_values_validate_literals_and_input_defaults(wf, field, value, templated):
    add_image_model(wf, quality=None)
    fake = Fake(None, [], ["openai/gpt-image-2"])

    def handle(request):
        response = fake.handle(request)
        if request.url.path.endswith("/images/models"):
            body = response.json()
            body["data"][0]["supported_parameters"][field]["values"] = ["medium" if field == "quality" else "1K" if field == "resolution" else "1:1"]
            return httpx.Response(200, json=body)
        return response

    path = image_scenario(wf, {field: "{{ inputs.x }}" if templated else value},
                          {"x": {"type": "string", "default": value}} if templated else None)
    with pytest.raises(ConfigErrors, match=f"does not support {field} {value}") as error:
        validate(path, transport=httpx.MockTransport(handle))
    if templated:
        assert "input default for x" in str(error.value)


@pytest.mark.parametrize("supported", [{}, {"quality": {"type": "enum"}}])
def test_missing_model_values_accept_parameter(wf, supported):
    add_image_model(wf, quality=None)
    path = image_scenario(wf, {"quality": "high"})
    transport = httpx.MockTransport(lambda request: httpx.Response(200, json={"data": [{
        "id": "openai/gpt-image-2", "architecture": {"output_modalities": ["image"]},
        "supported_parameters": supported,
    }]}))
    assert validate(path, transport=transport)


def test_template_without_default_and_reference_types(wf):
    add_image_model(wf)
    path = image_scenario(wf, {"quality": "{{ inputs.x }}"}, {"x": {"type": "string", "required": True}})
    assert validate(path, transport=Fake(None, [], ["openai/gpt-image-2"]).transport())
    path = image_scenario(wf, {"quality": "{{ inputs.x }}"}, {"x": {"type": "integer", "required": True}})
    with pytest.raises(ConfigErrors, match="template must return a string"):
        validate(path, check_models=False)
    path = image_scenario(wf, {"quality": "{{ inputs.missing }}"})
    with pytest.raises(ConfigErrors, match="missing"):
        validate(path, check_models=False)


@pytest.mark.parametrize("value,valid", [("medium", True), ("{{ inputs.x }}", True), ("ultra", False), (512, False)])
def test_schema_quality(wf, value, valid):
    path = image_scenario(wf, {"quality": value})
    assert bool(scenario_schema_errors(yaml.safe_load(path.read_text()), str(path))) is not valid
