package devops.authorization

decision := {"allow": allowed, "policy_revision": "authorization-v1", "reason": reason} if {
	results := [
		data.devops.identity.allow,
		data.devops.projects.allow,
		data.devops.resources.allow,
		data.devops.applications.allow,
	]
	every result in results {
		is_boolean(result)
	}
	allowed := true in results
}

reason := "not_found" if {
	data.devops.resources.target_not_found
} else := "not_found" if {
	data.devops.applications.target_not_found
} else := "ownership" if {
	data.devops.resources.ownership_denied
} else := "ownership" if {
	data.devops.applications.ownership_denied
} else := null
