package devops.projects

default allow := false

project_read_actions := {
	"devops_platform.application.projects.get_project.query.ReadProject",
	"devops_platform.application.projects.list_projects.query.ReadProjects",
}

allow if {
	input.action in project_read_actions
	input.subject.role in {"developer", "admin"}
	"resources:read" in input.subject.scopes
	input.subject.project_id == input.resource.project_id
	is_string(input.resource.project_id)
	input.resource.project_id != ""
}

allow if {
	input.action == "devops_platform.application.project_access.list_project_members.query.ListProjectMembers"
	input.subject.role == "admin"
	"resources:read" in input.subject.scopes
	input.subject.project_id == input.resource.project_id
	is_string(input.resource.project_id)
	input.resource.project_id != ""
}

allow if {
	input.action == "devops_platform.application.project_access.manage_project_membership.command.ManageProjectMembership"
	input.subject.role == "admin"
	"resources:write" in input.subject.scopes
	input.subject.project_id == input.resource.project_id
	is_string(input.resource.project_id)
	input.resource.project_id != ""
}

allow if {
	input.action == "devops_platform.application.projects.list_projects.query.ReadProjects"
	is_string(input.subject.id)
	input.subject.id != ""
	input.resource.project_id == null
}
