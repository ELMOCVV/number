import hashlib
from typing import Any, Awaitable, Callable

from aiogram import BaseMiddleware, F, Router
from aiogram.filters import Command, CommandStart, StateFilter
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.types import (
    CallbackQuery,
    InlineKeyboardButton,
    InlineKeyboardMarkup,
    KeyboardButton,
    Message,
    ReplyKeyboardMarkup,
    TelegramObject,
)

import db

router = Router()

BTN_ADD = "➕ Добавить"
BTN_LIST = "📋 Все номера"
BTN_SEARCH = "🔍 Найти"


class AccessMiddleware(BaseMiddleware):
    def __init__(self, allowed_ids: set[int]):
        self.allowed_ids = allowed_ids

    async def __call__(
        self,
        handler: Callable[[TelegramObject, dict[str, Any]], Awaitable[Any]],
        event: TelegramObject,
        data: dict[str, Any],
    ) -> Any:
        user = data.get("event_from_user")
        if user is None or user.id not in self.allowed_ids:
            return None
        return await handler(event, data)


class AddContact(StatesGroup):
    name = State()
    phone = State()
    department = State()
    confirm = State()


class Search(StatesGroup):
    query = State()


class EditContact(StatesGroup):
    value = State()


def dept_hash(name: str) -> str:
    # В callback_data влезает 64 байта, названия цехов — произвольный текст,
    # поэтому в кнопках ходит хэш, а имя восстанавливается из БД.
    return hashlib.md5(name.encode()).hexdigest()[:12]


def resolve_dept(h: str) -> str | None:
    for dept, _ in db.get_departments():
        if dept_hash(dept) == h:
            return dept
    return None


def canonical_dept(text: str) -> str:
    # Совпадение с существующим цехом без учёта регистра — берём его написание.
    for dept, _ in db.get_departments():
        if dept.lower() == text.lower():
            return dept
    return text


def main_menu() -> ReplyKeyboardMarkup:
    return ReplyKeyboardMarkup(
        keyboard=[
            [
                KeyboardButton(text=BTN_ADD),
                KeyboardButton(text=BTN_LIST),
                KeyboardButton(text=BTN_SEARCH),
            ]
        ],
        resize_keyboard=True,
    )


def depts_kb(prefix: str = "dept") -> InlineKeyboardMarkup | None:
    depts = db.get_departments()
    if not depts:
        return None
    rows = []
    for dept, cnt in depts:
        text = f"{dept} ({cnt})" if prefix == "dept" else dept
        rows.append(
            [InlineKeyboardButton(text=text, callback_data=f"{prefix}:{dept_hash(dept)}")]
        )
    return InlineKeyboardMarkup(inline_keyboard=rows)


def contacts_kb(contacts: list, back_cb: str | None = None) -> InlineKeyboardMarkup:
    rows = [
        [
            InlineKeyboardButton(
                text=f"{c['name']} — {c['phone']}", callback_data=f"card:{c['id']}"
            )
        ]
        for c in contacts
    ]
    if back_cb:
        rows.append([InlineKeyboardButton(text="⬅️ Назад", callback_data=back_cb)])
    return InlineKeyboardMarkup(inline_keyboard=rows)


def card_text(c) -> str:
    return f"👤 {c['name']}\n📞 {c['phone']}\n🏭 {c['department']}"


def card_kb(c) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(text="✏️ Изменить", callback_data=f"edit:{c['id']}"),
                InlineKeyboardButton(text="🗑 Удалить", callback_data=f"del:{c['id']}"),
            ],
            [
                InlineKeyboardButton(
                    text="⬅️ Назад", callback_data=f"dept:{dept_hash(c['department'])}"
                )
            ],
        ]
    )


# --- Общие команды и главное меню (сбрасывают любое состояние) ---


@router.message(CommandStart())
async def cmd_start(message: Message, state: FSMContext):
    await state.clear()
    await message.answer(
        "Справочник телефонов завода.\nВыберите действие:", reply_markup=main_menu()
    )


@router.message(Command("cancel"))
async def cmd_cancel(message: Message, state: FSMContext):
    await state.clear()
    await message.answer("Отменено.", reply_markup=main_menu())


@router.message(Command("add"))
@router.message(F.text == BTN_ADD)
async def add_start(message: Message, state: FSMContext):
    await state.clear()
    await state.set_state(AddContact.name)
    await message.answer("Введите имя:")


@router.message(F.text == BTN_LIST)
async def list_departments(message: Message, state: FSMContext):
    await state.clear()
    kb = depts_kb()
    if kb is None:
        await message.answer("Справочник пуст. Добавьте первый контакт: ➕ Добавить")
        return
    await message.answer("Подразделения:", reply_markup=kb)


@router.message(Command("search"))
@router.message(F.text == BTN_SEARCH)
async def search_start(message: Message, state: FSMContext):
    await state.clear()
    await state.set_state(Search.query)
    await message.answer("Введите имя или часть номера:")


# --- Добавление контакта ---


@router.message(AddContact.name, F.text)
async def add_name(message: Message, state: FSMContext):
    await state.update_data(name=message.text.strip())
    await state.set_state(AddContact.phone)
    await message.answer("Введите номер телефона:")


@router.message(AddContact.phone, F.text)
async def add_phone(message: Message, state: FSMContext):
    await state.update_data(phone=message.text.strip())
    await state.set_state(AddContact.department)
    kb = depts_kb(prefix="pick")
    await message.answer(
        "Укажите цех/склад/отдел (или выберите из существующих):"
        if kb
        else "Укажите цех/склад/отдел:",
        reply_markup=kb,
    )


async def show_preview(message: Message, state: FSMContext):
    data = await state.get_data()
    await state.set_state(AddContact.confirm)
    kb = InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(text="✅ Сохранить", callback_data="save"),
                InlineKeyboardButton(text="❌ Отменить", callback_data="cancel"),
            ]
        ]
    )
    await message.answer(
        f"Проверьте:\n👤 {data['name']}\n📞 {data['phone']}\n🏭 {data['department']}",
        reply_markup=kb,
    )


@router.message(AddContact.department, F.text)
async def add_department_text(message: Message, state: FSMContext):
    await state.update_data(department=canonical_dept(message.text.strip()))
    await show_preview(message, state)


@router.callback_query(AddContact.department, F.data.startswith("pick:"))
async def add_department_pick(callback: CallbackQuery, state: FSMContext):
    dept = resolve_dept(callback.data.split(":", 1)[1])
    if dept is None:
        await callback.answer("Цех не найден, введите текстом", show_alert=True)
        return
    await state.update_data(department=dept)
    await callback.answer()
    await show_preview(callback.message, state)


@router.callback_query(AddContact.confirm, F.data == "save")
async def add_save(callback: CallbackQuery, state: FSMContext):
    data = await state.get_data()
    db.add_contact(data["name"], data["phone"], data["department"])
    await state.clear()
    await callback.message.edit_text(
        f"✅ Сохранено:\n👤 {data['name']}\n📞 {data['phone']}\n🏭 {data['department']}"
    )
    await callback.answer("Сохранено")


@router.callback_query(AddContact.confirm, F.data == "cancel")
async def add_cancel(callback: CallbackQuery, state: FSMContext):
    await state.clear()
    await callback.message.edit_text("❌ Отменено.")
    await callback.answer()


# --- Просмотр по цехам ---


@router.callback_query(F.data == "depts")
async def cb_departments(callback: CallbackQuery):
    kb = depts_kb()
    if kb is None:
        await callback.message.edit_text("Справочник пуст.")
    else:
        await callback.message.edit_text("Подразделения:", reply_markup=kb)
    await callback.answer()


@router.callback_query(F.data.startswith("dept:"))
async def cb_department(callback: CallbackQuery):
    dept = resolve_dept(callback.data.split(":", 1)[1])
    if dept is None:
        await callback.answer("Цех не найден", show_alert=True)
        return
    contacts = db.get_contacts_by_department(dept)
    await callback.message.edit_text(
        f"🏭 {dept} — {len(contacts)} конт.:",
        reply_markup=contacts_kb(contacts, back_cb="depts"),
    )
    await callback.answer()


@router.callback_query(F.data.startswith("card:"))
async def cb_card(callback: CallbackQuery, state: FSMContext):
    await state.clear()
    c = db.get_contact(int(callback.data.split(":", 1)[1]))
    if c is None:
        await callback.answer("Контакт не найден", show_alert=True)
        return
    await callback.message.edit_text(card_text(c), reply_markup=card_kb(c))
    await callback.answer()


# --- Редактирование ---


@router.callback_query(F.data.startswith("edit:"))
async def cb_edit(callback: CallbackQuery):
    cid = int(callback.data.split(":", 1)[1])
    kb = InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(text="Имя", callback_data=f"editf:{cid}:name"),
                InlineKeyboardButton(text="Номер", callback_data=f"editf:{cid}:phone"),
                InlineKeyboardButton(text="Цех", callback_data=f"editf:{cid}:department"),
            ],
            [InlineKeyboardButton(text="⬅️ Назад", callback_data=f"card:{cid}")],
        ]
    )
    await callback.message.edit_reply_markup(reply_markup=kb)
    await callback.answer()


@router.callback_query(F.data.startswith("editf:"))
async def cb_edit_field(callback: CallbackQuery, state: FSMContext):
    _, cid, field = callback.data.split(":")
    await state.set_state(EditContact.value)
    await state.update_data(contact_id=int(cid), field=field)
    prompts = {
        "name": "Введите новое имя:",
        "phone": "Введите новый номер:",
        "department": "Укажите новый цех/склад/отдел:",
    }
    kb = depts_kb(prefix="pick") if field == "department" else None
    await callback.message.answer(prompts[field], reply_markup=kb)
    await callback.answer()


async def apply_edit(message: Message, state: FSMContext, value: str):
    data = await state.get_data()
    await state.clear()
    db.update_contact(data["contact_id"], data["field"], value)
    c = db.get_contact(data["contact_id"])
    await message.answer(f"✅ Обновлено.\n\n{card_text(c)}", reply_markup=card_kb(c))


@router.message(EditContact.value, F.text)
async def edit_value_text(message: Message, state: FSMContext):
    data = await state.get_data()
    value = message.text.strip()
    if data["field"] == "department":
        value = canonical_dept(value)
    await apply_edit(message, state, value)


@router.callback_query(EditContact.value, F.data.startswith("pick:"))
async def edit_value_pick(callback: CallbackQuery, state: FSMContext):
    dept = resolve_dept(callback.data.split(":", 1)[1])
    if dept is None:
        await callback.answer("Цех не найден, введите текстом", show_alert=True)
        return
    await callback.answer()
    await apply_edit(callback.message, state, dept)


# --- Удаление ---


@router.callback_query(F.data.startswith("delok:"))
async def cb_delete_confirmed(callback: CallbackQuery):
    cid = int(callback.data.split(":", 1)[1])
    c = db.get_contact(cid)
    if c is None:
        await callback.answer("Контакт не найден", show_alert=True)
        return
    db.delete_contact(cid)
    kb = InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text="⬅️ К подразделениям", callback_data="depts")]
        ]
    )
    await callback.message.edit_text(f"🗑 Удалён: {c['name']} — {c['phone']}", reply_markup=kb)
    await callback.answer("Удалено")


@router.callback_query(F.data.startswith("del:"))
async def cb_delete(callback: CallbackQuery):
    cid = int(callback.data.split(":", 1)[1])
    c = db.get_contact(cid)
    if c is None:
        await callback.answer("Контакт не найден", show_alert=True)
        return
    kb = InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(text="🗑 Да, удалить", callback_data=f"delok:{cid}"),
                InlineKeyboardButton(text="Отмена", callback_data=f"card:{cid}"),
            ]
        ]
    )
    await callback.message.edit_text(
        f"Удалить контакт?\n\n{card_text(c)}", reply_markup=kb
    )
    await callback.answer()


# --- Поиск ---


@router.message(Search.query, F.text)
async def search_query(message: Message, state: FSMContext):
    await state.clear()
    results = db.search_contacts(message.text.strip())
    if not results:
        await message.answer("Ничего не найдено.", reply_markup=main_menu())
        return
    await message.answer(
        f"Найдено: {len(results)}", reply_markup=contacts_kb(results)
    )


# --- Фолбэк ---


@router.message(StateFilter(None), F.text)
async def fallback(message: Message):
    await message.answer("Используйте кнопки меню ниже 👇", reply_markup=main_menu())
