package devops.resources

test_default_deny if { allow == false }

test_resource_read_requires_scope if {
	result := allow with input as {"subject": {"id": "u1", "role": "developer", "project_id": "p1", "scopes": ["resources:read"]}, "action": "devops_platform.application.resource_management.get_resource.query.ReadResource", "resource": {"kind": "resources", "project_id": "p1", "exists": true}}
	result
}

test_owner_write_allowed if {
	result := allow with input as {"subject": {"id": "u1", "role": "developer", "project_id": "p1", "scopes": ["resources:write"]}, "action": "devops_platform.application.resource_management.renew_lease.command.RenewDatabase", "resource": {"kind": "resources", "project_id": "p1", "owner_id": "u1", "exists": true}}
	result
}

test_other_owner_write_denied if {
	result := allow with input as {"subject": {"id": "u1", "role": "developer", "project_id": "p1", "scopes": ["resources:write"]}, "action": "devops_platform.application.resource_management.renew_lease.command.RenewDatabase", "resource": {"kind": "resources", "project_id": "p1", "owner_id": "u2", "exists": true}}
	result == false
}

test_ownership_denied_is_distinct_from_scope_failure if {
	ownership_denied with input as {"subject": {"id": "u1", "role": "developer", "project_id": "p1", "scopes": ["resources:write"]}, "action": "devops_platform.application.resource_management.renew_lease.command.RenewDatabase", "resource": {"kind": "resources", "project_id": "p1", "owner_id": "u2", "exists": true}}
}

test_missing_write_scope_is_not_ownership_denied if {
	result := ownership_denied with input as {"subject": {"id": "u1", "role": "developer", "project_id": "p1", "scopes": []}, "action": "devops_platform.application.resource_management.renew_lease.command.RenewDatabase", "resource": {"kind": "resources", "project_id": "p1", "owner_id": "u2", "exists": true}}
	result == false
}

test_missing_target_is_not_found_after_scope_gate if {
	target_not_found with input as {"subject": {"id": "u1", "role": "developer", "project_id": "p1", "scopes": ["resources:read"]}, "action": "devops_platform.application.resource_management.get_resource.query.ReadResource", "resource": {"kind": "resources", "project_id": "p1", "exists": false}}
}

test_missing_scope_precedes_missing_target if {
	result := target_not_found with input as {"subject": {"id": "u1", "role": "developer", "project_id": "p1", "scopes": []}, "action": "devops_platform.application.resource_management.get_resource.query.ReadResource", "resource": {"kind": "resources", "project_id": "p1", "exists": false}}
	result == false
}

test_admin_owner_override_is_same_project_only if {
	result := allow with input as {"subject": {"id": "admin", "role": "admin", "project_id": "p1", "scopes": ["resources:write"]}, "action": "devops_platform.application.resource_management.renew_lease.command.RenewDatabase", "resource": {"kind": "resources", "project_id": "p1", "owner_id": "u2", "exists": true}}
	result
}

test_foreign_target_remains_hidden_from_admin if {
	result := allow with input as {"subject": {"id": "admin", "role": "admin", "project_id": "p1", "scopes": ["resources:write"]}, "action": "devops_platform.application.resource_management.renew_lease.command.RenewDatabase", "resource": {"kind": "resources", "project_id": "p2", "owner_id": "u2", "exists": false}}
	result == false
}

test_existing_target_without_owner_fact_is_denied if {
	result := allow with input as {"subject": {"id": "u1", "role": "developer", "project_id": "p1", "scopes": ["resources:write"]}, "action": "devops_platform.application.resource_management.renew_lease.command.RenewDatabase", "resource": {"kind": "resources", "project_id": "p1", "exists": true}}
	result == false
}
