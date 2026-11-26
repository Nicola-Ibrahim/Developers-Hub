package devops.projects

test_default_deny if { allow == false }

test_scoped_project_read if {
	result := allow with input as {"subject": {"id": "u1", "role": "developer", "project_id": "p1", "scopes": ["resources:read"]}, "action": "devops_platform.application.projects.get_project.query.ReadProject", "resource": {"kind": "projects", "project_id": "p1"}}
	result
}

test_other_project_denied if {
	result := allow with input as {"subject": {"id": "u1", "role": "developer", "project_id": "p1", "scopes": ["resources:read"]}, "action": "devops_platform.application.projects.get_project.query.ReadProject", "resource": {"kind": "projects", "project_id": "p2"}}
	result == false
}

test_empty_project_list_has_authenticated_decision if {
	result := allow with input as {"subject": {"id": "u1"}, "action": "devops_platform.application.projects.list_projects.query.ReadProjects", "resource": {"kind": "projects", "project_id": null}}
	result
}

test_member_list_requires_admin if {
	result := allow with input as {"subject": {"id": "u1", "role": "developer", "project_id": "p1", "scopes": ["resources:read"]}, "action": "devops_platform.application.project_access.list_project_members.query.ListProjectMembers", "resource": {"kind": "projects", "project_id": "p1"}}
	result == false
}

test_member_manage_requires_admin if {
	result := allow with input as {"subject": {"id": "u1", "role": "developer", "project_id": "p1", "scopes": ["resources:write"]}, "action": "devops_platform.application.project_access.manage_project_membership.command.ManageProjectMembership", "resource": {"kind": "projects", "project_id": "p1"}}
	result == false
}
