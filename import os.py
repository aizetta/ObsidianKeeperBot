import os
import re
import logging
import datetime
import asyncio
from telegram import Update, InlineKeyboardMarkup, InlineKeyboardButton
from telegram.ext import (
    ApplicationBuilder,
    CommandHandler,
    CallbackQueryHandler,
    MessageHandler,
    ConversationHandler,
    ContextTypes,
    filters,
)
import git  # GitPython для работы с git

# -------------------- Конфигурация --------------------
BOT_TOKEN = "7750568426:AAHVidt7_QhBxgiDvHWFsP_hV3BJ5N2QVP8"
if not BOT_TOKEN:
    raise ValueError("Переменная окружения BOT_TOKEN не задана!")

REPO_PATH = '/Users/aizetta/Documents/Obsidian Vault/Obsidian/Артем'
ATTACHMENTS_PATH = os.path.join(REPO_PATH, 'attachments')
if not os.path.exists(ATTACHMENTS_PATH):
    os.makedirs(ATTACHMENTS_PATH)

# Шаблоны заметок (первая строка – название, далее поля)
templates = {
    "Шаблон 1": ["Название заметки", "Текст заметки"],
    "Шаблон 2": ["Название заметки", "Описание", "Текст заметки"]
}

# -------------------- Логирование --------------------
logging.basicConfig(
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    level=logging.INFO
)
logger = logging.getLogger(__name__)

# -------------------- Определение состояний --------------------
(MAIN_MENU, NOTE_TEXT, TAGS_INPUT, NOTE_PREVIEW, SEARCH_INPUT,
 REMINDER_INPUT, FILE_ATTACHMENT, TEMPLATE_MENU, FILL_TEMPLATE,
 TEMPLATE_PREVIEW, FOLDER_MENU_TEMPLATE, FOLDER_MENU_NORMAL,
 VIEW_NOTES, VIEW_NOTE) = range(14)

# -------------------- Вспомогательные функции --------------------
def sanitize_filename(name: str) -> str:
    """Возвращает безопасное имя файла."""
    name = name.strip().replace(' ', '_')
    return re.sub(r'(?u)[^-\w.]', '', name)

def push_to_github():
    """Выполняет commit и push с помощью GitPython."""
    try:
        repo = git.Repo(REPO_PATH)
        repo.git.add(all=True)
        commit_message = f"Добавлена новая заметка {datetime.datetime.now().strftime('%Y-%m-%d %H:%M:%S')}"
        repo.index.commit(commit_message)
        origin = repo.remote(name='origin')
        origin.push()
        logger.info("Git push выполнен успешно")
    except Exception as e:
        logger.error(f"Ошибка при push в GitHub: {e}")

def single_main_menu_button() -> InlineKeyboardMarkup:
    """Возвращает клавиатуру с единственной кнопкой '🏠 Главное меню'."""
    return InlineKeyboardMarkup([[InlineKeyboardButton("🏠 Главное меню", callback_data='main_menu')]])

def build_keyboard(rows: list) -> InlineKeyboardMarkup:
    """Упрощённое создание клавиатуры из списка рядов."""
    return InlineKeyboardMarkup(rows)

# -------------------- Основные обработчики --------------------
async def show_main_menu(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """
    Отображает главное меню, в котором:
      - выводятся корневые (текущей) папки;
      - доступны действия: создать заметку, создать заметку по шаблону, поиск, просмотр заметок, переход назад.
    """
    if 'current_folder' not in context.user_data:
        context.user_data['current_folder'] = REPO_PATH
    current_folder = context.user_data['current_folder']
    try:
        folders = [f for f in os.listdir(current_folder)
                   if os.path.isdir(os.path.join(current_folder, f)) and not (f.startswith('.') or f.startswith('_'))]
    except Exception as e:
        await (update.message or update.callback_query).reply_text(f"❗ Ошибка доступа к папке: {e}")
        folders = []

    kb = []
    # Кнопки с папками (каждая в отдельном ряду)
    for folder in folders:
        kb.append([InlineKeyboardButton(f"📁 {folder}", callback_data=f'folder:{folder}')])
    # Ряд с основными действиями (без дублирования главного меню)
    kb.append([
        InlineKeyboardButton("📝 Создать заметку", callback_data='create_note'),
        InlineKeyboardButton("📋 Создать заметку из шаблона", callback_data='create_template')
    ])
    kb.append([
        InlineKeyboardButton("🔍 Поиск", callback_data='search'),
        InlineKeyboardButton("👀 Просмотр заметок", callback_data='view_notes')
    ])
    # Если не в корневой папке – добавляем ряд с кнопкой "🔙 Назад" и отдельно "🏠 Главное меню"
    if os.path.abspath(current_folder) != os.path.abspath(REPO_PATH):
        kb.append([
            InlineKeyboardButton("🔙 Назад", callback_data='back'),
            InlineKeyboardButton("🏠 Главное меню", callback_data='main_menu')
        ])
    markup = build_keyboard(kb)
    text = f"📂 Текущая папка: {current_folder}\nВыберите папку или действие:"
    if update.message:
        await update.message.reply_text(text, reply_markup=markup)
    elif update.callback_query:
        await update.callback_query.edit_message_text(text, reply_markup=markup)
    return MAIN_MENU

async def main_menu_handler(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Обрабатывает нажатия в главном меню."""
    query = update.callback_query
    await query.answer()
    data = query.data
    if data.startswith('folder:'):
        folder_name = data.split(":", 1)[1]
        current_folder = context.user_data.get('current_folder', REPO_PATH)
        new_folder = os.path.join(current_folder, folder_name)
        if os.path.isdir(new_folder):
            context.user_data['current_folder'] = new_folder
        return await show_main_menu(update, context)
    elif data == 'back':
        current_folder = context.user_data.get('current_folder', REPO_PATH)
        parent_folder = os.path.dirname(current_folder)
        # Если родительская папка находится в пределах корневой директории
        if os.path.commonpath([REPO_PATH, os.path.abspath(parent_folder)]) == os.path.abspath(REPO_PATH):
            context.user_data['current_folder'] = parent_folder
        else:
            context.user_data['current_folder'] = REPO_PATH
        return await show_main_menu(update, context)
    elif data == 'create_note':
        await query.edit_message_text("📝 Введите текст заметки.\nПервая строка станет заголовком:\n\n(Для возврата в главное меню нажмите 🏠)", reply_markup=single_main_menu_button())
        return NOTE_TEXT
    elif data == 'search':
        await query.edit_message_text("🔍 Введите ключевое слово для поиска заметок:\n\n(🏠 Главное меню)", reply_markup=single_main_menu_button())
        return SEARCH_INPUT
    elif data == 'view_notes':
        return await show_view_notes_menu(update, context)
    elif data == 'create_template':
        return await show_template_menu(update, context)
    elif data == 'main_menu':
        return await show_main_menu(update, context)
    else:
        await query.edit_message_text("❗ Неверный выбор.", reply_markup=single_main_menu_button())
        return MAIN_MENU

# -------------------- Создание обычной заметки --------------------
async def note_text_handler(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Сохраняет введённый текст заметки и переходит к вводу тегов."""
    note_text = update.message.text
    if not note_text:
        await update.message.reply_text("❗ Текст заметки не может быть пустым. Повторите ввод:")
        return NOTE_TEXT
    context.user_data['note_text'] = note_text
    await update.message.reply_text("🏷️ Введите теги через запятую (можно оставить пустым):\n\n(🏠 Главное меню)", reply_markup=single_main_menu_button())
    return TAGS_INPUT

async def tags_input_handler(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Обрабатывает ввод тегов и выводит предварительный просмотр заметки."""
    tags_text = update.message.text
    tags = [tag.strip() for tag in tags_text.split(',')] if tags_text else []
    context.user_data['tags'] = tags
    note_text = context.user_data.get('note_text', '')
    preview = f"👁️ Предварительный просмотр:\n\n{note_text}\n"
    if tags:
        preview += f"\n🏷️ Теги: {', '.join(tags)}"
    kb = [
        [
            InlineKeyboardButton("💾 Сохранить", callback_data='save_note_default'),
            InlineKeyboardButton("📂 Выбрать папку", callback_data='choose_folder_note')
        ],
        [
            InlineKeyboardButton("✏️ Редактировать", callback_data='edit_note'),
            InlineKeyboardButton("📎 Прикрепить файл", callback_data='attach_note_file')
        ]
    ]
    # Добавляем единственную кнопку "🏠 Главное меню" в отдельном ряду
    kb.append([InlineKeyboardButton("🏠 Главное меню", callback_data='main_menu')])
    await update.message.reply_text(preview, reply_markup=build_keyboard(kb))
    return NOTE_PREVIEW

async def note_preview_handler(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Обрабатывает выбор в предварительном просмотре заметки."""
    query = update.callback_query
    await query.answer()
    data = query.data
    if data == 'save_note_default':
        note_text = context.user_data.get('note_text', '')
        tags = context.user_data.get('tags', [])
        title = note_text.splitlines()[0] if note_text.splitlines() else "Без_названия"
        safe_title = sanitize_filename(title)
        timestamp = datetime.datetime.now().strftime("%Y%m%d_%H%M%S")
        filename = f"{safe_title}_{timestamp}.md"
        current_folder = context.user_data.get('current_folder', REPO_PATH)
        filepath = os.path.join(current_folder, filename)
        if tags:
            note_text += f"\n\n🏷️ Теги: {', '.join(tags)}"
        try:
            with open(filepath, 'w', encoding='utf-8') as f:
                f.write(note_text)
            push_to_github()
            await query.edit_message_text(f"✅ Заметка сохранена: {filepath}\nИ синхронизирована с GitHub.", reply_markup=single_main_menu_button())
        except Exception as e:
            await query.edit_message_text(f"❗ Ошибка при сохранении заметки: {e}", reply_markup=single_main_menu_button())
        return await show_main_menu(update, context)
    elif data == 'choose_folder_note':
        return await show_folder_menu_normal(query, context)
    elif data == 'edit_note':
        await query.edit_message_text("✏️ Введите новый текст заметки:\n\n(🏠 Главное меню)", reply_markup=single_main_menu_button())
        return NOTE_TEXT
    elif data == 'attach_note_file':
        await query.edit_message_text("📎 Отправьте файл для прикрепления:\n\n(🏠 Главное меню)", reply_markup=single_main_menu_button())
        return FILE_ATTACHMENT
    elif data == 'main_menu':
        return await show_main_menu(update, context)
    else:
        await query.edit_message_text("❗ Неверный выбор.", reply_markup=single_main_menu_button())
        return NOTE_PREVIEW

async def file_attachment_handler(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Прикрепляет файл к заметке и возвращает к предварительному просмотру."""
    if update.message.document:
        document = update.message.document
        file = await document.get_file()
        file_path = os.path.join(ATTACHMENTS_PATH, document.file_name)
        await file.download_to_drive(custom_path=file_path)
        note_text = context.user_data.get('note_text', '')
        note_text += f"\n\n📎 Вложение: {file_path}"
        context.user_data['note_text'] = note_text
        await update.message.reply_text(f"✅ Файл прикреплён: {file_path}", reply_markup=single_main_menu_button())
    elif update.message.photo:
        photo = update.message.photo[-1]
        file = await photo.get_file()
        file_name = f"photo_{datetime.datetime.now().strftime('%Y%m%d_%H%M%S')}.jpg"
        file_path = os.path.join(ATTACHMENTS_PATH, file_name)
        await file.download_to_drive(custom_path=file_path)
        note_text = context.user_data.get('note_text', '')
        note_text += f"\n\n📎 Фото: {file_path}"
        context.user_data['note_text'] = note_text
        await update.message.reply_text(f"✅ Фото прикреплено: {file_path}", reply_markup=single_main_menu_button())
    else:
        await update.message.reply_text("❗ Нет файла. Повторите попытку.", reply_markup=single_main_menu_button())
        return FILE_ATTACHMENT
    return await note_preview_handler(update, context)

async def show_folder_menu_normal(query, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Выводит меню выбора папки для сохранения заметки."""
    current_folder = context.user_data.get('current_folder', REPO_PATH)
    try:
        folders = [f for f in os.listdir(current_folder)
                   if os.path.isdir(os.path.join(current_folder, f)) and not (f.startswith('.') or f.startswith('_'))]
    except Exception as e:
        await query.edit_message_text(f"❗ Ошибка доступа к папке: {e}")
        return NOTE_PREVIEW
    kb = []
    for folder in folders:
        kb.append([InlineKeyboardButton(f"📁 {folder}", callback_data=f'normal_folder:{folder}')])
    kb.append([InlineKeyboardButton("🔙 Назад", callback_data='normal_back'),
               InlineKeyboardButton("🏠 Главное меню", callback_data='main_menu')])
    await query.edit_message_text(f"📂 Текущая папка: {current_folder}\nВыберите папку для сохранения заметки:", reply_markup=build_keyboard(kb))
    return FOLDER_MENU_NORMAL

async def normal_folder_callback(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Сохраняет заметку в выбранной папке."""
    query = update.callback_query
    await query.answer()
    data = query.data
    if data.startswith('normal_folder:'):
        folder_name = data.split(":", 1)[1]
        current_folder = context.user_data.get('current_folder', REPO_PATH)
        new_folder = os.path.join(current_folder, folder_name)
        if os.path.isdir(new_folder):
            context.user_data['current_folder'] = new_folder
        else:
            await query.edit_message_text("❗ Папка не найдена.")
            return await show_folder_menu_normal(query, context)
        note_text = context.user_data.get('note_text', '')
        tags = context.user_data.get('tags', [])
        title = note_text.splitlines()[0] if note_text.splitlines() else "Без_названия"
        safe_title = sanitize_filename(title)
        timestamp = datetime.datetime.now().strftime("%Y%m%d_%H%M%S")
        filename = f"{safe_title}_{timestamp}.md"
        filepath = os.path.join(new_folder, filename)
        if tags:
            note_text += f"\n\n🏷️ Теги: {', '.join(tags)}"
        try:
            with open(filepath, 'w', encoding='utf-8') as f:
                f.write(note_text)
            push_to_github()
            await query.edit_message_text(f"✅ Заметка сохранена: {filepath}", reply_markup=single_main_menu_button())
        except Exception as e:
            await query.edit_message_text(f"❗ Ошибка при сохранении заметки: {e}", reply_markup=single_main_menu_button())
        return await show_main_menu(update, context)
    elif data == 'normal_back':
        return await note_preview_handler(update, context)
    elif data == 'main_menu':
        return await show_main_menu(update, context)
    else:
        await query.edit_message_text("❗ Неверный выбор.", reply_markup=single_main_menu_button())
        return FOLDER_MENU_NORMAL

# -------------------- Просмотр заметок --------------------
async def show_view_notes_menu(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Выводит список заметок (.md файлов) в текущей папке."""
    current_folder = context.user_data.get('current_folder', REPO_PATH)
    try:
        files = [f for f in os.listdir(current_folder)
                 if os.path.isfile(os.path.join(current_folder, f)) and f.endswith('.md')]
    except Exception as e:
        await update.callback_query.edit_message_text(f"❗ Ошибка доступа к папке: {e}")
        files = []
    text = f"👀 Заметки в папке: {current_folder}" if files else "❗ В текущей папке нет заметок."
    kb = []
    for file in files:
        kb.append([InlineKeyboardButton(f"📄 {file}", callback_data=f'view_note:{file}')])
    kb.append([InlineKeyboardButton("🔙 Назад", callback_data='main_menu')])
    await update.callback_query.edit_message_text(text, reply_markup=build_keyboard(kb))
    return VIEW_NOTES

async def view_note_handler(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Выводит содержимое выбранной заметки с кнопками возврата."""
    query = update.callback_query
    await query.answer()
    data = query.data
    if data.startswith('view_note:'):
        file_name = data.split(":", 1)[1]
        current_folder = context.user_data.get('current_folder', REPO_PATH)
        file_path = os.path.join(current_folder, file_name)
        try:
            with open(file_path, 'r', encoding='utf-8') as f:
                content = f.read()
            text = f"📄 Содержимое заметки {file_name}:\n\n{content}"
        except Exception as e:
            text = f"❗ Ошибка при чтении файла: {e}"
        kb = [
            [InlineKeyboardButton("🔙 Назад к списку", callback_data='view_notes')],
            [InlineKeyboardButton("🏠 Главное меню", callback_data='main_menu')]
        ]
        await query.edit_message_text(text, reply_markup=build_keyboard(kb))
        return VIEW_NOTE
    elif data == 'view_notes':
        return await show_view_notes_menu(update, context)
    elif data == 'main_menu':
        return await show_main_menu(update, context)
    else:
        await query.edit_message_text("❗ Неверный выбор.", reply_markup=single_main_menu_button())
        return VIEW_NOTES

# -------------------- Поиск заметок --------------------
async def search_input_handler(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Ищет заметки по ключевому слову во всех .md файлах репозитория."""
    keyword = update.message.text
    if not keyword:
        await update.message.reply_text("❗ Ключевое слово не может быть пустым.", reply_markup=single_main_menu_button())
        return SEARCH_INPUT
    results = []
    for root, dirs, files in os.walk(REPO_PATH):
        for file in files:
            if file.endswith('.md'):
                filepath = os.path.join(root, file)
                try:
                    with open(filepath, 'r', encoding='utf-8') as f:
                        content = f.read()
                    if keyword.lower() in content.lower():
                        results.append(os.path.relpath(filepath, REPO_PATH))
                except Exception as e:
                    logger.error(f"Ошибка при чтении файла {filepath}: {e}")
    result_text = "🔍 Найденные заметки:\n" + "\n".join(results) if results else "❗ Ничего не найдено."
    await update.message.reply_text(result_text, reply_markup=single_main_menu_button())
    return await show_main_menu(update, context)

# -------------------- Шаблоны заметок --------------------
async def show_template_menu(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Выводит меню выбора шаблона."""
    kb = []
    for tmpl in templates.keys():
        kb.append([InlineKeyboardButton(f"📋 {tmpl}", callback_data=f'template:{tmpl}')])
    kb.append([InlineKeyboardButton("🔙 Назад", callback_data='main_menu')])
    await (update.callback_query or update.message).reply_text("Выберите шаблон заметки:", reply_markup=build_keyboard(kb))
    return TEMPLATE_MENU

async def template_menu_handler(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Обрабатывает выбор шаблона и начинает его заполнение."""
    query = update.callback_query
    await query.answer()
    data = query.data
    if data.startswith('template:'):
        tmpl_name = data.split(":", 1)[1]
        context.user_data['selected_template'] = tmpl_name
        context.user_data['template_fields'] = templates[tmpl_name]
        context.user_data['template_data'] = []
        context.user_data['template_index'] = 0
        first_field = context.user_data['template_fields'][0]
        await query.edit_message_text(f"✏️ Заполните поле: {first_field}\n\n(🏠 Главное меню)", reply_markup=single_main_menu_button())
        return FILL_TEMPLATE
    elif data == 'main_menu':
        return await show_main_menu(update, context)
    else:
        await query.edit_message_text("❗ Неверный выбор.", reply_markup=single_main_menu_button())
        return TEMPLATE_MENU

async def fill_template_handler(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Заполняет шаблон по шагам и выводит предварительный просмотр."""
    user_input = update.message.text
    if not user_input:
        await update.message.reply_text("❗ Значение не может быть пустым.", reply_markup=single_main_menu_button())
        return FILL_TEMPLATE
    context.user_data['template_data'].append(user_input)
    context.user_data['template_index'] += 1
    fields = context.user_data['template_fields']
    if context.user_data['template_index'] < len(fields):
        next_field = fields[context.user_data['template_index']]
        await update.message.reply_text(f"✏️ Заполните поле: {next_field}\n\n(🏠 Главное меню)", reply_markup=single_main_menu_button())
        return FILL_TEMPLATE
    else:
        note_title = context.user_data['template_data'][0]
        note_body = "\n".join(context.user_data['template_data'][1:]) if len(context.user_data['template_data']) > 1 else ""
        preview = f"👁️ Предварительный просмотр шаблонной заметки:\n\nНазвание: {note_title}\nТекст: {note_body}"
        kb = [
            [InlineKeyboardButton("📂 Выбрать папку", callback_data='choose_folder_template')],
            [InlineKeyboardButton("✏️ Редактировать", callback_data='edit_template')]
        ]
        kb.append([InlineKeyboardButton("🏠 Главное меню", callback_data='main_menu')])
        await update.message.reply_text(preview, reply_markup=build_keyboard(kb))
        context.user_data['note_text'] = f"{note_title}\n{note_body}"
        context.user_data['note_title'] = note_title
        return TEMPLATE_PREVIEW

async def template_preview_handler(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Обрабатывает выбор после предварительного просмотра шаблонной заметки."""
    query = update.callback_query
    await query.answer()
    data = query.data
    if data == 'choose_folder_template':
        return await show_folder_menu_template(query, context)
    elif data == 'edit_template':
        await query.edit_message_text("✏️ Введите новое значение для заметки:\n\n(🏠 Главное меню)", reply_markup=single_main_menu_button())
        context.user_data['template_data'] = []
        context.user_data['template_index'] = 0
        first_field = context.user_data['template_fields'][0]
        await query.message.reply_text(f"✏️ Заполните поле: {first_field}\n\n(🏠 Главное меню)", reply_markup=single_main_menu_button())
        return FILL_TEMPLATE
    elif data == 'main_menu':
        return await show_main_menu(update, context)
    else:
        await query.edit_message_text("❗ Неверный выбор.", reply_markup=single_main_menu_button())
        return TEMPLATE_PREVIEW

async def show_folder_menu_template(query, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Выводит меню выбора папки для сохранения шаблонной заметки."""
    current_folder = context.user_data.get('current_folder', REPO_PATH)
    try:
        folders = [f for f in os.listdir(current_folder)
                   if os.path.isdir(os.path.join(current_folder, f)) and not (f.startswith('.') or f.startswith('_'))]
    except Exception as e:
        await query.edit_message_text(f"❗ Ошибка доступа к папке: {e}")
        return TEMPLATE_PREVIEW
    kb = []
    for folder in folders:
        kb.append([InlineKeyboardButton(f"📁 {folder}", callback_data=f'template_folder:{folder}')])
    kb.append([InlineKeyboardButton("🔙 Назад", callback_data='template_back')])
    kb.append([InlineKeyboardButton("🏠 Главное меню", callback_data='main_menu')])
    await query.edit_message_text(f"📂 Текущая папка: {current_folder}\nВыберите папку для сохранения шаблонной заметки:", reply_markup=build_keyboard(kb))
    return FOLDER_MENU_TEMPLATE

async def template_folder_callback(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Сохраняет шаблонную заметку в выбранной папке."""
    query = update.callback_query
    await query.answer()
    data = query.data
    if data.startswith('template_folder:'):
        folder_name = data.split(":", 1)[1]
        current_folder = context.user_data.get('current_folder', REPO_PATH)
        new_folder = os.path.join(current_folder, folder_name)
        if os.path.isdir(new_folder):
            context.user_data['current_folder'] = new_folder
        else:
            await query.edit_message_text("❗ Папка не найдена.")
            return await show_folder_menu_template(query, context)
        note_text = context.user_data.get('note_text', '')
        note_title = context.user_data.get('note_title', 'Без_названия')
        safe_title = sanitize_filename(note_title)
        timestamp = datetime.datetime.now().strftime("%Y%m%d_%H%M%S")
        filename = f"{safe_title}_{timestamp}.md"
        filepath = os.path.join(new_folder, filename)
        try:
            with open(filepath, 'w', encoding='utf-8') as f:
                f.write(note_text)
            push_to_github()
            await query.edit_message_text(f"✅ Шаблонная заметка сохранена: {filepath}", reply_markup=single_main_menu_button())
        except Exception as e:
            await query.edit_message_text(f"❗ Ошибка при сохранении заметки: {e}", reply_markup=single_main_menu_button())
        return await show_main_menu(update, context)
    elif data == 'template_back':
        return await template_preview_handler(update, context)
    elif data == 'main_menu':
        return await show_main_menu(update, context)
    else:
        await query.edit_message_text("❗ Неверный выбор.", reply_markup=single_main_menu_button())
        return FOLDER_MENU_TEMPLATE

# -------------------- Отмена действия --------------------
async def cancel(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Отменяет текущее действие и возвращает в главное меню."""
    if update.message:
        await update.message.reply_text("❗ Действие отменено.", reply_markup=single_main_menu_button())
    return await show_main_menu(update, context)

# -------------------- Основная функция --------------------
async def main() -> None:
    application = ApplicationBuilder().token(BOT_TOKEN).build()

    conv_handler = ConversationHandler(
        entry_points=[CommandHandler('start', show_main_menu)],
        states={
            MAIN_MENU: [CallbackQueryHandler(main_menu_handler)],
            NOTE_TEXT: [MessageHandler(filters.TEXT & ~filters.COMMAND, note_text_handler)],
            TAGS_INPUT: [MessageHandler(filters.TEXT & ~filters.COMMAND, tags_input_handler)],
            NOTE_PREVIEW: [CallbackQueryHandler(note_preview_handler)],
            SEARCH_INPUT: [MessageHandler(filters.TEXT & ~filters.COMMAND, search_input_handler)],
            FILE_ATTACHMENT: [MessageHandler(filters.ALL, file_attachment_handler)],
            TEMPLATE_MENU: [CallbackQueryHandler(template_menu_handler)],
            FILL_TEMPLATE: [MessageHandler(filters.TEXT & ~filters.COMMAND, fill_template_handler)],
            TEMPLATE_PREVIEW: [CallbackQueryHandler(template_preview_handler)],
            FOLDER_MENU_TEMPLATE: [CallbackQueryHandler(template_folder_callback)],
            FOLDER_MENU_NORMAL: [CallbackQueryHandler(normal_folder_callback)],
            VIEW_NOTES: [CallbackQueryHandler(view_note_handler)],
            VIEW_NOTE: [CallbackQueryHandler(view_note_handler)]
        },
        fallbacks=[CommandHandler('cancel', cancel)]
    )

    application.add_handler(conv_handler)
    await application.run_polling()

if __name__ == '__main__':
    import nest_asyncio
    nest_asyncio.apply()
    import asyncio
    asyncio.run(main())
