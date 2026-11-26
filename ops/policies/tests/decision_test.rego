package devops.authorization

test_default_deny if {
	decision.allow == false
}

test_unknown_operation_denied_for_privileged_subject if {
	verified := {
		"action": "devops_platform.unregistered.ManageEverything",
		"subject": {"id": "user", "project_id": "project", "role": "admin", "scopes": ["resources:write"]},
		"resource": {"kind": "resources", "project_id": "project", "owner_id": "user"},
	}
	result := decision with input as verified
	result.allow == false
}

test_policy_revision if {
	decision.policy_revision == "authorization-v1"
}

test_target_not_found_reason if {
	result := decision with input as {
		"subject": {"id": "u1", "role": "developer", "project_id": "p1", "scopes": ["resources:read"]},
		"action": "devops_platform.application.resource_management.get_resource.query.ReadResource",
		"resource": {"kind": "resources", "project_id": "p1", "exists": false},
	}
	result.allow == false
	result.reason == "not_found"
}

test_owner_denial_reason if {
	result := decision with input as {
		"subject": {"id": "u1", "role": "developer", "project_id": "p1", "scopes": ["resources:write"]},
		"action": "devops_platform.application.resource_management.renew_lease.command.RenewDatabase",
		"resource": {"kind": "resources", "project_id": "p1", "owner_id": "u2", "exists": true},
	}
	result.allow == false
	result.reason == "ownership"
}

test_malformed_package_decision_is_undefined if {
	not decision with data.devops.identity.allow as null
}
