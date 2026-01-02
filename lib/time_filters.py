def is_time_allowed(current_time, allowed_hours_list):
    if not allowed_hours_list: return True # Si la lista está vacía, opera siempre
    return current_time.hour in allowed_hours_list