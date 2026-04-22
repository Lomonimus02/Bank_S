import json

USER_DATA_FILE = "user_data.json"

def load_user_data():
    try:
        with open(USER_DATA_FILE, "r") as f:
            return json.load(f)
    except FileNotFoundError:
        return {}
    except json.JSONDecodeError:
        print("Ошибка: user_data.json поврежден.")
        return {}  # Или обработайте ошибку по-другому

def save_user_data(user_data):
    with open(USER_DATA_FILE, "w") as f:
        json.dump(user_data, f)

def update_existing_users():
    user_data = load_user_data()
    if not user_data:
        print("Данные пользователя пусты")
        return
    for user_id, user in user_data.items():
        # Добавляем отсутствующие поля со значениями по умолчанию
        if "F" not in user:
            user["F"] = 0.0
        if "Y" not in user:
            user["Y"] = 0.0
        if "last_p_update" not in user:
            user["last_p_update"] = None
        if 'last_burn_check' not in user:
            user['last_burn_check'] = None

        # Добавьте сюда любые другие отсутствующие поля, если необходимо

    save_user_data(user_data)
    print("Данные пользователя успешно обновлены.")

if __name__ == "__main__":
    update_existing_users()