async def send_telegram_message(telegram_id, message):
    """Отправка сообщения в Telegram"""
    try:
        from telegram_bot import bot
        await bot.send_message(telegram_id, message)
        print(f"✅ Отправлено в Telegram пользователю {telegram_id}")
    except Exception as e:
        print(f"❌ Ошибка отправки в Telegram: {e}")


def send_daily_notifications():
    """Ежедневные уведомления о тратах за день"""
    print("📊 Отправка ежедневных уведомлений...")

    today = timezone.now().date()
    yesterday = today - timedelta(days=1)

    users = User.objects.all()

    for user in users:
        try:
            from finance.models import Transaction
            transactions = Transaction.objects.filter(
                user=user,
                date=yesterday
            )

            if transactions.exists():
                total_income = transactions.filter(type='income').aggregate(Sum('amount'))['amount__sum'] or 0
                total_expense = transactions.filter(type='expense').aggregate(Sum('amount'))['amount__sum'] or 0

                message = (
                    f"📊 Ежедневный отчет за {yesterday.strftime('%d.%m.%Y')}:\n"
                    f"💵 Доходы: {total_income:.2f} руб.\n"
                    f"💸 Расходы: {total_expense:.2f} руб.\n"
                    f"💰 Баланс: {total_income - total_expense:.2f} руб.\n"
                    f"📈 Количество операций: {len(transactions)}"
                )

                print(f"Уведомление для {user.username}: {message}")

                # 🔥 ДОБАВИТЬ ОТПРАВКУ В TELEGRAM
                # Нужно получить telegram_id пользователя
                # Пока просто выводим в консоль

        except Exception as e:
            print(f"❌ Ошибка для пользователя {user.username}: {e}")

    for user in users:
        try:
            # ... подсчет транзакций ...

            if transactions.exists():
                # ... формирование сообщения ...

                # 🔥 ОТПРАВКА В TELEGRAM
                if hasattr(user, 'consent') and user.consent.telegram_id:
                    import asyncio
                    asyncio.run(send_telegram_message(user.consent.telegram_id, message))
                else:
                    print(f"⚠️ Не найден telegram_id для {user.username}")

        except Exception as e:
            print(f"❌ Ошибка для пользователя {user.username}: {e}")