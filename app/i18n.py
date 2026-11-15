"""Patient-facing strings: en, fi, sv, ar, ru written by hand; Somali is AI-translated on demand and cached (English fallback).
All patient wording is plain and calm. Review with native speakers before real use."""
import json
import re

from app import llm

EN = {
    "chat_title": "Ask your nurse", "chat_intro": "Write to {nurse}. A nurse reads every message and answers you herself. This is not an emergency line.", "chat_ph": "Write your question here", "chat_send": "Send", "chat_you": "You", "chat_empty": "No messages yet. Your questions and the answers will be here.", "chat_received": "{nurse} has your message and will answer within one working day. If it is urgent, call.", "chat_urgent": "If you have severe pain, trouble breathing, heavy bleeding or feel unsafe, call 112 now.", "chat_q_when": "When is my next appointment?", "chat_q_who": "Who do I call?", "chat_quick": "Quick answers", "chat_other": "Something else", "chat_who_a": "Your nurse is {nurse}. You can call her from this page.", "chat_waiting": "Waiting for {nurse}", "reply_ack": "Thank you for your question. I will call you today or the next working day to go through it. {nurse}",
    "notes": "Notes", "hi": "Hi {name}", "lang": "Language", "next": "Next step", "arranging": "We are arranging your next appointment. {nurse} will tell you.",
    "interp": "Interpreter booked", "nurse": "Your nurse", "call": "Call", "called": "Calling {nurse} (demo)",
    "slipped": "My date slipped", "slip_done": "{nurse} has been told and will call you today or the next working day.",
    "message": "Message from {nurse}", "listen": "Listen", "no_audio": "Voice is not available right now.",
    "pulse_title": "A few quick questions", "of": "{a} of {b}", "thanks": "Thank you", "thanks_sub": "{nurse} will see your answers.",
    "heard": "I heard: “{heard}”", "is_right": "Is that right?", "yes": "Yes", "no": "No", "unsure": "Not sure", "speak": "Speak your answer",
    "listening": "Listening… tap to stop", "try_tap": "I could not understand. Please tap an answer.", "wait": "Working on it…",
    "all_good": "You are on your path.", "done": "Done", "synthetic": "Demo with invented data",
    "step_T0": "Suspicion noted", "step_T1": "Referral sent", "step_T2": "Referral received", "step_T4": "Results talk", "step_T5": "Team review", "step_T6": "Treatment",
    "test_lung": "CT scan", "test_breast": "Recall imaging", "test_colorectal": "Colonoscopy", "test_prostate": "MRI scan", "test_haematological": "Blood test",
    "q_PU1": "When did you first notice it?", "q_PU2": "How many times have you contacted us about this?", "q_PU3": "What made it hard?",
    "q_PU4": "Do you know what happens next?", "q_PU5a": "Did you try to reach your nurse?", "q_PU5": "Could you reach your nurse within 1 working day?", "q_PU6": "Were you understood in your language?",
    "q_PU7": "How worried have you been this week? 0 is not at all, 10 is extremely.", "q_PU8": "How many times did you have to repeat your story?",
    "q_PU9": "How likely are you to recommend this care to a friend? 0 to 10.", "q_PU9b": "What most affected your experience?",
    "opt_PU1_week": "This week", "opt_PU1_w2_4": "2 to 4 weeks ago", "opt_PU1_m1_3": "1 to 3 months ago", "opt_PU1_m3p": "Over 3 months ago",
    "opt_PU2_1": "Once", "opt_PU2_2": "Twice", "opt_PU2_3p": "3 or more times",
    "opt_PU3_time": "Time", "opt_PU3_cost": "Cost", "opt_PU3_language": "Language", "opt_PU3_fear": "Fear", "opt_PU3_noappt": "No appointment", "opt_PU3_notserious": "Did not seem serious",
    "opt_PU4_yes": "Yes", "opt_PU4_unsure": "Not sure", "opt_PU4_no": "No",
    "opt_PU5a_yes": "Yes", "opt_PU5a_no": "No", "opt_PU5a_not_tried": "I haven't tried", "opt_PU5_yes": "Yes", "opt_PU5_no": "No", "opt_PU6_yes": "Yes", "opt_PU6_partly": "Partly", "opt_PU6_no": "No",
    "opt_PU9b_skip": "Skip", "pulse_text_ph": "Write a short answer", "pulse_submit": "Save answer",
    "opt_PU8_0": "Never", "opt_PU8_1": "Once", "opt_PU8_2": "Twice", "opt_PU8_3p": "3 or more times",
}
FI = {
    "chat_title": "Kysy hoitajalta", "chat_intro": "Kirjoita hoitajalle {nurse}. Hoitaja lukee jokaisen viestin ja vastaa itse. Tämä ei ole hätänumero.", "chat_ph": "Kirjoita kysymyksesi tähän", "chat_send": "Lähetä", "chat_you": "Sinä", "chat_empty": "Ei vielä viestejä. Kysymyksesi ja vastaukset näkyvät tässä.", "chat_received": "{nurse} on saanut viestisi ja vastaa viimeistään seuraavana arkipäivänä. Jos asia on kiireellinen, soita.", "chat_urgent": "Jos sinulla on kova kipu, hengitysvaikeuksia, runsasta verenvuotoa tai tunnet olosi turvattomaksi, soita heti 112.", "chat_q_when": "Milloin on seuraava aikani?", "chat_q_who": "Kenelle soitan?", "chat_quick": "Pikavastaukset", "chat_other": "Jotain muuta", "chat_who_a": "Hoitajasi on {nurse}. Voit soittaa hänelle tältä sivulta.", "chat_waiting": "Odotetaan: {nurse}", "reply_ack": "Kiitos kysymyksestäsi. Soitan sinulle tänään tai seuraavana arkipäivänä ja käymme asian läpi. {nurse}",
    "notes": "Huomautukset", "hi": "Hei {name}", "lang": "Kieli", "next": "Seuraava vaihe", "arranging": "Järjestämme seuraavaa aikaa. {nurse} kertoo sinulle.",
    "interp": "Tulkki varattu", "nurse": "Hoitajasi", "call": "Soita", "called": "Soitetaan {nurse} (demo)",
    "slipped": "Aikani siirtyi", "slip_done": "{nurse} on saanut tiedon ja soittaa sinulle tänään tai seuraavana arkipäivänä.",
    "message": "Viesti: {nurse}", "listen": "Kuuntele", "no_audio": "Ääni ei ole juuri nyt käytettävissä.",
    "pulse_title": "Muutama nopea kysymys", "of": "{a} / {b}", "thanks": "Kiitos", "thanks_sub": "{nurse} näkee vastauksesi.",
    "heard": "Kuulin: “{heard}”", "is_right": "Onko se oikein?", "yes": "Kyllä", "no": "Ei", "unsure": "En ole varma", "speak": "Vastaa puhumalla",
    "listening": "Kuuntelen… napauta lopettaaksesi", "try_tap": "En ymmärtänyt. Valitse vastaus napauttamalla.", "wait": "Hetki…",
    "all_good": "Olet matkalla eteenpäin.", "done": "Valmis", "synthetic": "Demo keksityillä tiedoilla",
    "step_T0": "Epäily kirjattu", "step_T1": "Lähete lähetetty", "step_T2": "Lähete saapunut", "step_T4": "Tulosten käynti", "step_T5": "Tiimin arvio", "step_T6": "Hoito",
    "test_lung": "Keuhkojen TT-kuvaus", "test_breast": "Uusintakuvaus", "test_colorectal": "Kolonoskopia", "test_prostate": "MRI-kuvaus", "test_haematological": "Verikoe",
    "q_PU1": "Milloin huomasit oireen ensimmäisen kerran?", "q_PU2": "Montako kertaa olet ottanut yhteyttä tämän vuoksi?", "q_PU3": "Mikä teki asioinnista vaikeaa?",
    "q_PU4": "Tiedätkö, mitä seuraavaksi tapahtuu?", "q_PU5a": "Yrititkö tavoittaa hoitajasi?", "q_PU5": "Tavoititko hoitajasi yhden arkipäivän sisällä?", "q_PU6": "Ymmärrettiinkö sinua omalla kielelläsi?",
    "q_PU7": "Kuinka huolissasi olet ollut tällä viikolla? 0 ei lainkaan, 10 erittäin.", "q_PU8": "Montako kertaa jouduit kertomaan tarinasi uudelleen?",
    "q_PU9": "Kuinka todennäköisesti suosittelisit tätä hoitoa ystävällesi? 0–10.", "q_PU9b": "Mikä vaikutti kokemukseesi eniten?",
    "opt_PU1_week": "Tällä viikolla", "opt_PU1_w2_4": "2–4 viikkoa sitten", "opt_PU1_m1_3": "1–3 kuukautta sitten", "opt_PU1_m3p": "Yli 3 kuukautta sitten",
    "opt_PU2_1": "Kerran", "opt_PU2_2": "Kaksi kertaa", "opt_PU2_3p": "3 kertaa tai useammin",
    "opt_PU3_time": "Aika", "opt_PU3_cost": "Kustannukset", "opt_PU3_language": "Kieli", "opt_PU3_fear": "Pelko", "opt_PU3_noappt": "Ei aikaa saatavilla", "opt_PU3_notserious": "Ei vaikuttanut vakavalta",
    "opt_PU4_yes": "Kyllä", "opt_PU4_unsure": "En ole varma", "opt_PU4_no": "En",
    "opt_PU5a_yes": "Kyllä", "opt_PU5a_no": "En", "opt_PU5a_not_tried": "En ole yrittänyt", "opt_PU5_yes": "Kyllä", "opt_PU5_no": "En", "opt_PU6_yes": "Kyllä", "opt_PU6_partly": "Osittain", "opt_PU6_no": "Ei",
    "opt_PU9b_skip": "Ohita", "pulse_text_ph": "Kirjoita lyhyt vastaus", "pulse_submit": "Tallenna vastaus",
    "opt_PU8_0": "Ei kertaakaan", "opt_PU8_1": "Kerran", "opt_PU8_2": "Kaksi kertaa", "opt_PU8_3p": "3 kertaa tai useammin",
}
SV = {
    "chat_title": "Fråga din sjuksköterska", "chat_intro": "Skriv till {nurse}. En sjuksköterska läser varje meddelande och svarar själv. Det här är inte en nödlinje.", "chat_ph": "Skriv din fråga här", "chat_send": "Skicka", "chat_you": "Du", "chat_empty": "Inga meddelanden än. Dina frågor och svaren visas här.", "chat_received": "{nurse} har fått ditt meddelande och svarar senast nästa vardag. Ring om det är brådskande.", "chat_urgent": "Om du har svår smärta, andningssvårigheter, kraftig blödning eller känner dig otrygg, ring 112 direkt.", "chat_q_when": "När är min nästa tid?", "chat_q_who": "Vem ringer jag?", "chat_quick": "Snabba svar", "chat_other": "Något annat", "chat_who_a": "Din sjuksköterska är {nurse}. Du kan ringa henne från den här sidan.", "chat_waiting": "Väntar på {nurse}", "reply_ack": "Tack för din fråga. Jag ringer dig i dag eller nästa vardag så går vi igenom den. {nurse}",
    "notes": "Anmärkningar", "hi": "Hej {name}", "lang": "Språk", "next": "Nästa steg", "arranging": "Vi ordnar din nästa tid. {nurse} berättar för dig.",
    "interp": "Tolk bokad", "nurse": "Din sjuksköterska", "call": "Ring", "called": "Ringer {nurse} (demo)",
    "slipped": "Min tid ändrades", "slip_done": "{nurse} har fått veta och ringer dig i dag eller nästa vardag.",
    "message": "Meddelande från {nurse}", "listen": "Lyssna", "no_audio": "Rösten är inte tillgänglig just nu.",
    "pulse_title": "Några snabba frågor", "of": "{a} av {b}", "thanks": "Tack", "thanks_sub": "{nurse} ser dina svar.",
    "heard": "Jag hörde: “{heard}”", "is_right": "Stämmer det?", "yes": "Ja", "no": "Nej", "unsure": "Osäker", "speak": "Svara med rösten",
    "listening": "Lyssnar… tryck för att stoppa", "try_tap": "Jag förstod inte. Tryck på ett svar.", "wait": "Ett ögonblick…",
    "all_good": "Du är på väg framåt.", "done": "Klart", "synthetic": "Demo med påhittade uppgifter",
    "step_T0": "Misstanke noterad", "step_T1": "Remiss skickad", "step_T2": "Remiss mottagen", "step_T4": "Besked om resultat", "step_T5": "Teamgranskning", "step_T6": "Behandling",
    "test_lung": "Datortomografi", "test_breast": "Ny bildtagning", "test_colorectal": "Koloskopi", "test_prostate": "MR-undersökning", "test_haematological": "Blodprov",
    "q_PU1": "När märkte du det första gången?", "q_PU2": "Hur många gånger har du kontaktat oss om detta?", "q_PU3": "Vad gjorde det svårt?",
    "q_PU4": "Vet du vad som händer härnäst?", "q_PU5a": "Försökte du nå din sjuksköterska?", "q_PU5": "Kunde du nå din sjuksköterska inom 1 vardag?", "q_PU6": "Blev du förstådd på ditt språk?",
    "q_PU7": "Hur orolig har du varit den här veckan? 0 inte alls, 10 extremt.", "q_PU8": "Hur många gånger fick du upprepa din historia?",
    "q_PU9": "Hur sannolikt är det att du skulle rekommendera vården till en vän? 0–10.", "q_PU9b": "Vad påverkade din upplevelse mest?",
    "opt_PU1_week": "Den här veckan", "opt_PU1_w2_4": "För 2–4 veckor sedan", "opt_PU1_m1_3": "För 1–3 månader sedan", "opt_PU1_m3p": "För över 3 månader sedan",
    "opt_PU2_1": "En gång", "opt_PU2_2": "Två gånger", "opt_PU2_3p": "3 gånger eller fler",
    "opt_PU3_time": "Tid", "opt_PU3_cost": "Kostnad", "opt_PU3_language": "Språk", "opt_PU3_fear": "Rädsla", "opt_PU3_noappt": "Ingen tid fanns", "opt_PU3_notserious": "Verkade inte allvarligt",
    "opt_PU4_yes": "Ja", "opt_PU4_unsure": "Osäker", "opt_PU4_no": "Nej",
    "opt_PU5a_yes": "Ja", "opt_PU5a_no": "Nej", "opt_PU5a_not_tried": "Jag har inte försökt", "opt_PU5_yes": "Ja", "opt_PU5_no": "Nej", "opt_PU6_yes": "Ja", "opt_PU6_partly": "Delvis", "opt_PU6_no": "Nej",
    "opt_PU9b_skip": "Hoppa över", "pulse_text_ph": "Skriv ett kort svar", "pulse_submit": "Spara svar",
    "opt_PU8_0": "Aldrig", "opt_PU8_1": "En gång", "opt_PU8_2": "Två gånger", "opt_PU8_3p": "3 gånger eller fler",
}
AR = {
    "chat_title": "اسأل ممرضتك", "chat_intro": "اكتب إلى {nurse}. تقرأ الممرضة كل رسالة وتردّ بنفسها. هذا ليس خط طوارئ.", "chat_ph": "اكتب سؤالك هنا", "chat_send": "إرسال", "chat_you": "أنت", "chat_empty": "لا توجد رسائل بعد. ستظهر أسئلتك والردود هنا.", "chat_received": "وصلت رسالتك إلى {nurse} وستردّ خلال يوم عمل واحد. إذا كان الأمر عاجلًا فاتصل.", "chat_urgent": "إذا كنت تعاني من ألم شديد أو صعوبة في التنفس أو نزيف غزير أو تشعر بعدم الأمان، فاتصل بـ 112 فورًا.", "chat_q_when": "متى موعدي القادم؟", "chat_q_who": "بمن أتصل؟", "chat_quick": "إجابات سريعة", "chat_other": "شيء آخر", "chat_who_a": "ممرضتك هي {nurse}. يمكنك الاتصال بها من هذه الصفحة.", "chat_waiting": "في انتظار {nurse}", "reply_ack": "شكرًا على سؤالك. سأتصل بك اليوم أو في يوم العمل التالي لنراجعه معًا. {nurse}",
    "notes": "ملاحظات", "hi": "مرحبًا {name}", "lang": "اللغة", "next": "الخطوة التالية", "arranging": "نحن نرتّب موعدك القادم. ستخبرك {nurse}.",
    "interp": "تم حجز مترجم", "nurse": "ممرضتك", "call": "اتصال", "called": "الاتصال بـ {nurse} (تجريبي)",
    "slipped": "موعدي تأخّر", "slip_done": "تم إبلاغ {nurse} وستتصل بك اليوم أو في يوم العمل التالي.",
    "message": "رسالة من {nurse}", "listen": "استمع", "no_audio": "الصوت غير متاح حاليًا.",
    "pulse_title": "سؤالان سريعان", "of": "{a} من {b}", "thanks": "شكرًا لك", "thanks_sub": "ستطّلع {nurse} على إجاباتك.",
    "heard": "سمعتُ: «{heard}»", "is_right": "هل هذا صحيح؟", "yes": "نعم", "no": "لا", "unsure": "لست متأكدًا", "speak": "أجب بصوتك",
    "listening": "أستمع… اضغط للإيقاف", "try_tap": "لم أفهم. من فضلك اضغط على إجابة.", "wait": "لحظة…",
    "all_good": "أنت على المسار الصحيح.", "done": "تم", "synthetic": "عرض تجريبي ببيانات مختلقة",
    "step_T0": "تم تسجيل الاشتباه", "step_T1": "تم إرسال الإحالة", "step_T2": "تم استلام الإحالة", "step_T4": "جلسة النتائج", "step_T5": "مراجعة الفريق", "step_T6": "العلاج",
    "test_lung": "تصوير مقطعي", "test_breast": "تصوير إضافي", "test_colorectal": "تنظير القولون", "test_prostate": "تصوير بالرنين المغناطيسي", "test_haematological": "فحص دم",
    "q_PU1": "متى لاحظت ذلك لأول مرة؟", "q_PU2": "كم مرة تواصلت معنا بخصوص هذا؟", "q_PU3": "ما الذي جعل الأمر صعبًا؟",
    "q_PU4": "هل تعرف ما الذي سيحدث بعد ذلك؟", "q_PU5": "هل استطعت الوصول إلى ممرضتك خلال يوم عمل واحد؟", "q_PU6": "هل فهمك الجميع بلغتك؟",
    "q_PU7": "ما مدى قلقك هذا الأسبوع؟ 0 لا قلق، 10 قلق شديد.", "q_PU8": "كم مرة اضطررت إلى إعادة قصتك؟",
    "q_PU9": "ما مدى احتمال أن توصي بهذه الرعاية لصديق؟ من 0 إلى 10.",
    "opt_PU1_week": "هذا الأسبوع", "opt_PU1_w2_4": "قبل 2 إلى 4 أسابيع", "opt_PU1_m1_3": "قبل 1 إلى 3 أشهر", "opt_PU1_m3p": "قبل أكثر من 3 أشهر",
    "opt_PU2_1": "مرة واحدة", "opt_PU2_2": "مرتين", "opt_PU2_3p": "3 مرات أو أكثر",
    "opt_PU3_time": "الوقت", "opt_PU3_cost": "التكلفة", "opt_PU3_language": "اللغة", "opt_PU3_fear": "الخوف", "opt_PU3_noappt": "لا يوجد موعد", "opt_PU3_notserious": "لم يبدُ الأمر خطيرًا",
    "opt_PU4_yes": "نعم", "opt_PU4_unsure": "لست متأكدًا", "opt_PU4_no": "لا",
    "opt_PU5_yes": "نعم", "opt_PU5_no": "لا", "opt_PU6_yes": "نعم", "opt_PU6_partly": "جزئيًا", "opt_PU6_no": "لا",
    "opt_PU8_0": "أبدًا", "opt_PU8_1": "مرة واحدة", "opt_PU8_2": "مرتين", "opt_PU8_3p": "3 مرات أو أكثر",
}
RU = {
    "chat_title": "Спросите медсестру", "chat_intro": "Напишите {nurse}. Медсестра читает каждое сообщение и отвечает сама. Это не экстренная линия.", "chat_ph": "Напишите свой вопрос здесь", "chat_send": "Отправить", "chat_you": "Вы", "chat_empty": "Сообщений пока нет. Здесь будут ваши вопросы и ответы.", "chat_received": "{nurse} получила ваше сообщение и ответит в течение одного рабочего дня. Если это срочно, позвоните.", "chat_urgent": "Если у вас сильная боль, трудно дышать, сильное кровотечение или вы чувствуете опасность, звоните 112 прямо сейчас.", "chat_q_when": "Когда моя следующая запись?", "chat_q_who": "Кому звонить?", "chat_quick": "Быстрые ответы", "chat_other": "Другое", "chat_who_a": "Ваша медсестра — {nurse}. Вы можете позвонить ей с этой страницы.", "chat_waiting": "Ожидаем {nurse}", "reply_ack": "Спасибо за вопрос. Я позвоню вам сегодня или в следующий рабочий день, и мы всё обсудим. {nurse}",
    "notes": "Примечания", "hi": "Здравствуйте, {name}", "lang": "Язык", "next": "Следующий шаг", "arranging": "Мы организуем вашу следующую запись. {nurse} сообщит вам.",
    "interp": "Переводчик заказан", "nurse": "Ваша медсестра", "call": "Позвонить", "called": "Звоним {nurse} (демо)",
    "slipped": "Мою дату перенесли", "slip_done": "{nurse} получила сообщение и позвонит вам сегодня или в следующий рабочий день.",
    "message": "Сообщение от {nurse}", "listen": "Прослушать", "no_audio": "Голос сейчас недоступен.",
    "pulse_title": "Два коротких вопроса", "of": "{a} из {b}", "thanks": "Спасибо", "thanks_sub": "{nurse} увидит ваши ответы.",
    "heard": "Я услышал: «{heard}»", "is_right": "Это верно?", "yes": "Да", "no": "Нет", "unsure": "Не уверен", "speak": "Ответить голосом",
    "listening": "Слушаю… нажмите, чтобы остановить", "try_tap": "Я не понял. Пожалуйста, выберите ответ.", "wait": "Минутку…",
    "all_good": "Вы на верном пути.", "done": "Готово", "synthetic": "Демо с вымышленными данными",
    "step_T0": "Подозрение отмечено", "step_T1": "Направление отправлено", "step_T2": "Направление получено", "step_T4": "Беседа о результатах", "step_T5": "Обсуждение командой", "step_T6": "Лечение",
    "test_lung": "КТ", "test_breast": "Повторная визуализация", "test_colorectal": "Колоноскопия", "test_prostate": "МРТ", "test_haematological": "Анализ крови",
    "q_PU1": "Когда вы впервые это заметили?", "q_PU2": "Сколько раз вы обращались к нам по этому поводу?", "q_PU3": "Что вызвало трудности?",
    "q_PU4": "Вы знаете, что будет дальше?", "q_PU5": "Удалось ли вам связаться с медсестрой в течение 1 рабочего дня?", "q_PU6": "Вас поняли на вашем языке?",
    "q_PU7": "Насколько вы беспокоились на этой неделе? 0 — совсем нет, 10 — очень сильно.", "q_PU8": "Сколько раз вам пришлось повторять свою историю?",
    "q_PU9": "Насколько вероятно, что вы порекомендуете эту помощь другу? От 0 до 10.",
    "opt_PU1_week": "На этой неделе", "opt_PU1_w2_4": "2–4 недели назад", "opt_PU1_m1_3": "1–3 месяца назад", "opt_PU1_m3p": "Более 3 месяцев назад",
    "opt_PU2_1": "Один раз", "opt_PU2_2": "Два раза", "opt_PU2_3p": "3 раза и более",
    "opt_PU3_time": "Время", "opt_PU3_cost": "Стоимость", "opt_PU3_language": "Язык", "opt_PU3_fear": "Страх", "opt_PU3_noappt": "Не было записи", "opt_PU3_notserious": "Не казалось серьёзным",
    "opt_PU4_yes": "Да", "opt_PU4_unsure": "Не уверен", "opt_PU4_no": "Нет",
    "opt_PU5_yes": "Да", "opt_PU5_no": "Нет", "opt_PU6_yes": "Да", "opt_PU6_partly": "Частично", "opt_PU6_no": "Нет",
    "opt_PU8_0": "Ни разу", "opt_PU8_1": "Один раз", "opt_PU8_2": "Два раза", "opt_PU8_3p": "3 раза и более",
}
WEEKDAY = {
    "en": ["Monday", "Tuesday", "Wednesday", "Thursday", "Friday", "Saturday", "Sunday"],
    "fi": ["maanantai", "tiistai", "keskiviikko", "torstai", "perjantai", "lauantai", "sunnuntai"],
    "sv": ["måndag", "tisdag", "onsdag", "torsdag", "fredag", "lördag", "söndag"],
    "ar": ["الاثنين", "الثلاثاء", "الأربعاء", "الخميس", "الجمعة", "السبت", "الأحد"],
    "ru": ["понедельник", "вторник", "среда", "четверг", "пятница", "суббота", "воскресенье"],
}
EN.update({"ask": "Ask a question", "ask_ph": "Write your question here", "ask_send": "Send question", "ask_done": "{nurse} has your question and will call you.",
           "interp_band": "An interpreter has been booked for you.", "privacy": "Your answer goes to your own care team. If you tell us you are very worried, your nurse calls you within one working day.",
           "q_progress": "Question {a} of {b} · about 20 seconds", "speak_link": "Answer by speaking", "listen_link": "Listen",
           "unit_ct": "CT unit", "unit_imaging": "Imaging unit", "unit_colonoscopy": "Endoscopy unit", "unit_mri": "MRI unit", "unit_lab": "Laboratory"})
FI.update({"ask": "Esitä kysymys", "ask_ph": "Kirjoita kysymyksesi tähän", "ask_send": "Lähetä kysymys", "ask_done": "{nurse} on saanut kysymyksesi ja soittaa sinulle.",
           "interp_band": "Sinulle on varattu tulkki.", "privacy": "Vastauksesi menee omalle hoitotiimillesi. Jos kerrot olevasi hyvin huolissasi, hoitajasi soittaa sinulle yhden arkipäivän sisällä.",
           "q_progress": "Kysymys {a}/{b} · noin 20 sekuntia", "speak_link": "Vastaa puhumalla", "listen_link": "Kuuntele",
           "unit_ct": "TT-yksikkö", "unit_imaging": "Kuvantamisyksikkö", "unit_colonoscopy": "Endoskopiayksikkö", "unit_mri": "MRI-yksikkö", "unit_lab": "Laboratorio"})
SV.update({"ask": "Ställ en fråga", "ask_ph": "Skriv din fråga här", "ask_send": "Skicka frågan", "ask_done": "{nurse} har din fråga och ringer dig.",
           "interp_band": "En tolk har bokats åt dig.", "privacy": "Ditt svar går till ditt eget vårdteam. Om du säger att du är mycket orolig ringer din sjuksköterska inom en vardag.",
           "q_progress": "Fråga {a} av {b} · cirka 20 sekunder", "speak_link": "Svara genom att tala", "listen_link": "Lyssna",
           "unit_ct": "DT-enhet", "unit_imaging": "Bildenhet", "unit_colonoscopy": "Endoskopienhet", "unit_mri": "MR-enhet", "unit_lab": "Laboratorium"})
AR.update({"ask": "اطرح سؤالًا", "ask_ph": "اكتب سؤالك هنا", "ask_send": "أرسل السؤال", "ask_done": "{nurse} استلمت سؤالك وستتصل بك.",
           "interp_band": "تم حجز مترجم لك.", "privacy": "تذهب إجابتك إلى فريق رعايتك. إذا أخبرتنا أنك قلق جدًا، ستتصل بك ممرضتك خلال يوم عمل واحد.",
           "q_progress": "السؤال {a} من {b} · حوالي 20 ثانية", "speak_link": "أجب بالتحدث", "listen_link": "استمع",
           "unit_ct": "وحدة التصوير المقطعي", "unit_imaging": "وحدة التصوير", "unit_colonoscopy": "وحدة التنظير", "unit_mri": "وحدة الرنين المغناطيسي", "unit_lab": "المختبر"})
RU.update({"ask": "Задать вопрос", "ask_ph": "Напишите свой вопрос здесь", "ask_send": "Отправить вопрос", "ask_done": "{nurse} получила ваш вопрос и позвонит вам.",
           "interp_band": "Для вас заказан переводчик.", "privacy": "Ваш ответ получает только ваша медицинская команда. Если вы скажете, что очень волнуетесь, медсестра позвонит вам в течение одного рабочего дня.",
           "q_progress": "Вопрос {a} из {b} · около 20 секунд", "speak_link": "Ответить голосом", "listen_link": "Прослушать",
           "unit_ct": "Отделение КТ", "unit_imaging": "Отделение визуализации", "unit_colonoscopy": "Отделение эндоскопии", "unit_mri": "Отделение МРТ", "unit_lab": "Лаборатория"})
EN.update({"support": "You have your own nurse and a clear plan. You do not have to work out the next step alone.", "reassure_booked": "All you need to do is come to the appointment. Your nurse takes care of the rest.",
           "thanks_worry": "Thank you for telling us. {nurse} will call you today or on the next working day.", "step_of": "Step {a} of {b}", "call_nurse": "Call {nurse}",
           "slipped": "My appointment was moved", "opt_PU4_yes": "Yes, I know", "opt_PU4_unsure": "I am not sure", "opt_PU4_no": "Not yet", "thanks_sub": "{nurse} sees your answers and is here to help."})
FI.update({"support": "Sinulla on oma hoitaja ja selkeä suunnitelma. Sinun ei tarvitse selvittää seuraavaa askelta yksin.", "reassure_booked": "Sinun tarvitsee vain saapua vastaanotolle. Hoitajasi hoitaa loput.",
           "thanks_worry": "Kiitos, että kerroit. {nurse} soittaa sinulle tänään tai seuraavana arkipäivänä.", "step_of": "Vaihe {a} / {b}", "call_nurse": "Soita: {nurse}",
           "slipped": "Aikani siirtyi", "opt_PU4_yes": "Kyllä, tiedän", "opt_PU4_unsure": "En ole varma", "opt_PU4_no": "En vielä", "thanks_sub": "{nurse} näkee vastauksesi ja auttaa sinua."})
SV.update({"support": "Du har en egen sjuksköterska och en tydlig plan. Du behöver inte klura ut nästa steg själv.", "reassure_booked": "Du behöver bara komma till tiden. Din sjuksköterska sköter resten.",
           "thanks_worry": "Tack för att du berättade. {nurse} ringer dig i dag eller nästa vardag.", "step_of": "Steg {a} av {b}", "call_nurse": "Ring {nurse}",
           "slipped": "Min tid ändrades", "opt_PU4_yes": "Ja, jag vet", "opt_PU4_unsure": "Jag är osäker", "opt_PU4_no": "Inte ännu", "thanks_sub": "{nurse} ser dina svar och hjälper dig."})
AR.update({"support": "لديك ممرضتك الخاصة وخطة واضحة. لست مضطرًا إلى معرفة الخطوة التالية وحدك.", "reassure_booked": "كل ما عليك هو الحضور إلى الموعد. ممرضتك تتولى الباقي.",
           "thanks_worry": "شكرًا لأنك أخبرتنا. ستتصل بك {nurse} اليوم أو في يوم العمل التالي.", "step_of": "الخطوة {a} من {b}", "call_nurse": "اتصل بـ {nurse}",
           "slipped": "تغيّر موعدي", "opt_PU4_yes": "نعم، أعرف", "opt_PU4_unsure": "لست متأكدًا", "opt_PU4_no": "ليس بعد", "thanks_sub": "{nurse} ترى إجاباتك وهي هنا لمساعدتك."})
RU.update({"support": "У вас есть своя медсестра и понятный план. Вам не нужно разбираться в следующем шаге в одиночку.", "reassure_booked": "Вам нужно только прийти на приём. Остальное берёт на себя ваша медсестра.",
           "thanks_worry": "Спасибо, что рассказали. {nurse} позвонит вам сегодня или в следующий рабочий день.", "step_of": "Шаг {a} из {b}", "call_nurse": "Позвонить: {nurse}",
           "slipped": "Мою запись перенесли", "opt_PU4_yes": "Да, я знаю", "opt_PU4_unsure": "Не уверен", "opt_PU4_no": "Пока нет", "thanks_sub": "{nurse} видит ваши ответы и поможет вам."})
STATIC = {"en": EN, "fi": FI, "sv": SV, "ar": AR, "ru": RU}
NATIVE = {"en": "English", "fi": "Suomi", "sv": "Svenska", "ar": "العربية", "so": "Soomaali", "ru": "Русский"}
_cache = {}


def get(lang):
    """Return (strings, how). how: 'written' for hand-written languages, 'ai' for AI-translated, 'fallback' for English."""
    if lang in STATIC:
        return STATIC[lang], "written"
    if lang in _cache:
        return _cache[lang]
    out = (EN, "fallback")
    if lang == "so":
        prompt = ("Translate the VALUES of this JSON from English to Somali. Keep every key and every {placeholder} unchanged. "
                  "Plain, calm, simple words for a patient. Output only the JSON.\n\n" + json.dumps(EN, ensure_ascii=False))
        text, engine = llm.llm(prompt, max_tokens=6000)
        try:
            tr = json.loads(re.search(r"\{.*\}", text, re.S).group(0))
            if set(tr) >= set(EN):
                out = ({**EN, **tr}, "ai")
        except Exception:
            pass
    if out[1] == "ai":  # never cache a failure: try again next time
        _cache[lang] = out
    return out
