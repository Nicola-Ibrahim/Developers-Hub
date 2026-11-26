package devops.identity

default allow := false

allow if {
	is_string(input.subject.id)
	input.subject.id != ""
	input.subject.id == input.resource.owner_id
	input.action in {
		"identity.application.sessions.list_sessions.query.ListSessionsQuery",
		"identity.application.profile.profile_query.ProfileQuery",
		"identity.application.profile.profile_query.SecurityHistoryQuery",
		"identity.application.sessions.rotate_csrf.command.RotateCsrfCommand",
		"identity.application.authentication.logout.command.LogoutCommand",
		"identity.application.sessions.revoke_all_sessions.command.RevokeAllSessionsCommand",
		"identity.application.sessions.revoke_session.command.RevokeSessionCommand",
		"identity.application.accounts.change_password.command.ChangePasswordCommand",
		"identity.application.profile.update_profile.UpdateProfileCommand",
		"identity.application.api_tokens.personal_token_messages.ListPersonalTokensQuery",
		"identity.application.api_tokens.personal_token_messages.CreatePersonalTokenCommand",
		"identity.application.api_tokens.personal_token_messages.RotatePersonalTokenCommand",
		"identity.application.api_tokens.personal_token_messages.RevokePersonalTokenCommand",
	}
	input.resource.kind in {"session", "profile", "token"}
}

allow if {
	is_string(input.subject.id)
	input.subject.id != ""
	input.action == "identity.application.sessions.select_active_project.command.SelectActiveProjectCommand"
	input.resource.kind == "session"
	input.subject.id == input.resource.owner_id
	input.subject.role in {"developer", "admin"}
	input.subject.project_id == input.resource.project_id
	is_string(input.resource.project_id)
	input.resource.project_id != ""
}
