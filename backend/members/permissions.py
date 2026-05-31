def is_treasurer(user):
    return user.is_authenticated and user.groups.filter(name="Treasurer").exists()
