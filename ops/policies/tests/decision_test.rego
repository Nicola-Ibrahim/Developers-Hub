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

test_malformed_package_decision_is_undefined if {
	not decision with data.devops.identity.allow as null
}
