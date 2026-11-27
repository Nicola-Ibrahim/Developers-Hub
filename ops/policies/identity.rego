package devops.identity

default allow := false

allow if {
	is_string(input.subject.id)
	input.subject.id != ""
	input.subject.id == input.resource.owner_id
	input.action in {
		"identity.application.sessions.list_sessions.query.ListSessionsQuery",
		"identity.application.profile.read_profile.query.ProfileQuery",
		"identity.application.profile.security_history.query.SecurityHistoryQuery",
		"identity.application.sessions.rotate_csrf.command.RotateCsrfCommand",
		"identity.application.authentication.logout.command.LogoutCommand",
		"identity.application.sessions.revoke_all_sessions.command.RevokeAllSessionsCommand",
		"identity.application.sessions.revoke_session.command.RevokeSessionCommand",
		"identity.application.accounts.change_password.command.ChangePasswordCommand",
		"identity.application.profile.update_profile.command.UpdateProfileCommand",
		"identity.application.api_tokens.list_personal_tokens.query.ListPersonalTokensQuery",
		"identity.application.api_tokens.create_personal_token.command.CreatePersonalTokenCommand",
		"identity.application.api_tokens.rotate_personal_token.command.RotatePersonalTokenCommand",
		"identity.application.api_tokens.revoke_personal_token.command.RevokePersonalTokenCommand",
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
