from gateway.task_catalog import public_task_templates, resolve_task_request


def test_public_task_templates_expose_plugin_keys() -> None:
    templates = public_task_templates()
    assert templates
    assert all(item.get('pluginKey') for item in templates)


def test_continuous_plugin_resolves_without_target_category() -> None:
    resolved = resolve_task_request(template_id='clear-table', task_type=None, target_category=None)
    assert resolved.plugin_key == 'continuous'
    assert resolved.target_category is None
    assert resolved.place_profile == 'default'
