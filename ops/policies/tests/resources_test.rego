package devops.resources

test_default_deny if { allow == false }

test_resource_read_requires_scope if {
	result := allow with input as {"subject": {"id": "u1", "role": "developer", "project_id": "p1", "scopes": ["resources:read"]}, "action": "devops_platform.application.resource_management.get_resource.query.ReadResource", "resource": {"kind": "resources", "project_id": "p1"}}
	result
}

test_owner_write_allowed if {
	result := allow with input as {"subject": {"id": "u1", "role": "developer", "project_id": "p1", "scopes": ["resources:write"]}, "action": "devops_platform.application.resource_management.renew_lease.command.RenewDatabase", "resource": {"kind": "resources", "project_id": "p1", "owner_id": "u1"}}
	result
}

test_other_owner_write_denied if {
	result := allow with input as {"subject": {"id": "u1", "role": "developer", "project_id": "p1", "scopes": ["resources:write"]}, "action": "devops_platform.application.resource_management.renew_lease.command.RenewDatabase", "resource": {"kind": "resources", "project_id": "p1", "owner_id": "u2"}}
	result == false
}

test_ownership_denied_is_distinct_from_scope_failure if {
	ownership_denied with input as {"subject": {"id": "u1", "role": "developer", "project_id": "p1", "scopes": ["resources:write"]}, "action": "devops_platform.application.resource_management.renew_lease.command.RenewDatabase", "resource": {"kind": "resources", "project_id": "p1", "owner_id": "u2"}}
}

test_missing_write_scope_is_not_ownership_denied if {
	result := ownership_denied with input as {"subject": {"id": "u1", "role": "developer", "project_id": "p1", "scopes": []}, "action": "devops_platform.application.resource_management.renew_lease.command.RenewDatabase", "resource": {"kind": "resources", "project_id": "p1", "owner_id": "u2"}}
	result == false
}
