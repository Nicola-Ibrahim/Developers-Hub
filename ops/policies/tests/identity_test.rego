package devops.identity

test_profile_owner_allowed if {
	allow with input as {
		"subject": {"id": "user-a"},
		"action": "identity.application.profile.read_profile.query.ProfileQuery",
		"resource": {"kind": "profile", "owner_id": "user-a"},
	}
}

test_profile_other_owner_denied if {
	not allow with input as {
		"subject": {"id": "user-a"},
		"action": "identity.application.profile.read_profile.query.ProfileQuery",
		"resource": {"kind": "profile", "owner_id": "user-b"},
	}
}

test_session_owner_allowed if {
	allow with input as {
		"subject": {"id": "user-a"},
		"action": "identity.application.sessions.list_sessions.query.ListSessionsQuery",
		"resource": {"kind": "session", "owner_id": "user-a"},
	}
}

test_session_other_owner_denied if {
	not allow with input as {
		"subject": {"id": "user-a"},
		"action": "identity.application.sessions.list_sessions.query.ListSessionsQuery",
		"resource": {"kind": "session", "owner_id": "user-b"},
	}
}

test_token_other_owner_denied if {
	not allow with input as {
		"subject": {"id": "user-a"},
		"action": "identity.application.api_tokens.rotate_personal_token.command.RotatePersonalTokenCommand",
		"resource": {"kind": "token", "owner_id": "user-b"},
	}
}

test_missing_subject_denied if {
	not allow with input as {
		"subject": {"id": null},
		"action": "identity.application.sessions.list_sessions.query.ListSessionsQuery",
		"resource": {"kind": "session", "owner_id": null},
	}
}

test_select_current_membership_allowed if {
	allow with input as {
		"subject": {"id": "user-a", "project_id": "project-a", "role": "developer"},
		"action": "identity.application.sessions.select_active_project.command.SelectActiveProjectCommand",
		"resource": {"kind": "session", "owner_id": "user-a", "project_id": "project-a"},
	}
}

test_select_other_membership_denied if {
	not allow with input as {
		"subject": {"id": "user-a", "project_id": "project-a", "role": "developer"},
		"action": "identity.application.sessions.select_active_project.command.SelectActiveProjectCommand",
		"resource": {"kind": "session", "owner_id": "user-a", "project_id": "project-b"},
	}
}
