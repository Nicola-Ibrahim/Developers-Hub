package devops.applications

test_default_deny if { allow == false }

test_signed_webhook_operation_reaches_signature_verifier if {
	result := allow with input as {"subject": {"id": "00000000-0000-0000-0000-000000000000"}, "action": "devops_platform.application.software_delivery.handle_preview_webhook.command.ProcessGithubPreviewWebhook", "resource": {"kind": "verified_webhook"}}
	result
}

test_application_owner_read_allowed if {
	result := allow with input as {"subject": {"id": "u1", "role": "developer", "project_id": "p1", "scopes": ["resources:read"]}, "action": "devops_platform.application.applications.get_application.query.ReadApplication", "resource": {"kind": "applications", "project_id": "p1", "owner_id": "u1", "exists": true}}
	result
}

test_application_same_project_read_ignores_owner if {
	result := allow with input as {"subject": {"id": "u1", "role": "developer", "project_id": "p1", "scopes": ["resources:read"]}, "action": "devops_platform.application.applications.get_application.query.ReadApplication", "resource": {"kind": "applications", "project_id": "p1", "owner_id": "u2", "exists": true}}
	result
}

test_application_owned_write_denial_is_distinct if {
	ownership_denied with input as {"subject": {"id": "u1", "role": "developer", "project_id": "p1", "scopes": ["resources:write"]}, "action": "devops_platform.application.software_delivery.deploy_application.command.DeployApplication", "resource": {"kind": "applications", "project_id": "p1", "owner_id": "u2", "exists": true}}
}

test_application_write_missing_scope_is_not_ownership_denial if {
	result := ownership_denied with input as {"subject": {"id": "u1", "role": "developer", "project_id": "p1", "scopes": []}, "action": "devops_platform.application.software_delivery.deploy_application.command.DeployApplication", "resource": {"kind": "applications", "project_id": "p1", "owner_id": "u2", "exists": true}}
	result == false
}

test_missing_application_is_not_found_after_scope_gate if {
	target_not_found with input as {"subject": {"id": "u1", "role": "developer", "project_id": "p1", "scopes": ["resources:read"]}, "action": "devops_platform.application.applications.get_application.query.ReadApplication", "resource": {"kind": "applications", "project_id": "p1", "exists": false}}
}

test_missing_scope_precedes_missing_application if {
	result := target_not_found with input as {"subject": {"id": "u1", "role": "developer", "project_id": "p1", "scopes": []}, "action": "devops_platform.application.applications.get_application.query.ReadApplication", "resource": {"kind": "applications", "project_id": "p1", "exists": false}}
	result == false
}

test_creation_does_not_need_target_existence if {
	result := allow with input as {"subject": {"id": "u1", "role": "developer", "project_id": "p1", "scopes": ["resources:write"]}, "action": "devops_platform.application.applications.create_application.command.CreateApplication", "resource": {"kind": "applications", "project_id": "p1"}}
	result
}

test_webhook_without_verified_classification_denied if {
	result := allow with input as {"subject": {"id": "u1"}, "action": "devops_platform.application.software_delivery.handle_preview_webhook.command.ProcessGithubPreviewWebhook", "resource": {"kind": "applications"}}
	result == false
}
