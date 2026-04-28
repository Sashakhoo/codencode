import smtplib, csv, time, random
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
from datetime import datetime

# ── CONFIG ─────────────────────────────────────────
GMAIL_ADDRESS  = "codencodemy@gmail.com"
APP_PASSWORD   = "rfxn bssx ject owya"
SENDER_NAME    = "Sasha from codencode"
DELAY_SECONDS  = 60   
LOG_FILE       = "sent_log.csv"

# ── TEMPLATES ──────────────────────────────────────
# Each template has multiple subject line variants — one is picked randomly
# so bulk emails don't look identical if people compare notes

TEMPLATES = {

    # ── International & Private Schools (English) ──────────────────
    "en_school": {
        "subjects": [
            "Free Python & AI session for your students — no strings attached",
            "Quick question about your students and coding",
            "Can I visit {school_name} for 45 minutes?",
            "Something your students might actually enjoy",
        ],
        "body": """Hi {contact_name},

I'll keep this short — I know how full inboxes get.

My name is Sasha. I'm based in Johor Bahru and I run codencode Academy, a small coding school that teaches Python and AI in three languages — English, Mandarin, and Bahasa Melayu.

What I'm hoping to offer {school_name} is a free 50-minute session, in your auditorium or any classroom, where your students get to write real Python code and watch it talk to an AI — live, in front of them. No slides. No sales pitch. Just hands-on code.

The last school we visited had students asking to sign up before we even finished.

I'm not asking for anything today — just whether you'd be open to this kind of session. If yes, I'll work around your schedule completely.

Would you be the right person to talk to about this, or should I reach out to someone else?

Thanks for reading,
Sasha Khoo
Founder, codencode Academy
📱 +601131652854
🌐 codencode.my
📍 JB-based | Classes online via Zoom

P.S. We have a 4.7-star rating on Google from real students in JB — happy to share that if it helps."""
    },

    # ── Government / National Schools (Bahasa Melayu) ──────────────
    "bm_school": {
        "subjects": [
            "Permohonan Sesi Python & AI Percuma untuk Pelajar {school_name}",
            "Sesi Hands-On Pengkodan Percuma — Tiada Kos Kepada Sekolah",
            "Peluang Pengayaan ICT untuk Pelajar {school_name}",
        ],
        "body": """Yang Dihormati {contact_name},

Salam sejahtera dan salam hormat.

Nama saya Sasha Khoo, pengasas codencode Academy — akademi pengkodan yang berpusat di Johor Bahru. Kami mengajar Python dan AI dalam tiga bahasa: Bahasa Melayu, Bahasa Inggeris, dan Bahasa Mandarin.

Saya ingin memohon peluang untuk mengadakan sesi Python & AI percuma selama 50 minit untuk pelajar {school_name} — di dewan sekolah atau mana-mana bilik yang sesuai, pada masa yang senang untuk pihak sekolah.

Semasa sesi ini, pelajar akan:
• Menulis kod Python sebenar (bukan drag-and-drop)
• Melihat AI bertindak balas secara langsung di hadapan mereka
• Memahami mengapa kemahiran ini penting untuk masa depan mereka

Tiada kos langsung kepada sekolah. Tiada obligasi selepas sesi. Saya hanya ingin memberi pelajar {school_name} pendedahan awal kepada kemahiran yang semakin dicari dalam pasaran kerja hari ini.

Adakah tuan/puan berminat untuk saya hubungi bagi mengaturkan perkara ini?

Sekian, terima kasih atas masa tuan/puan.

Sasha Khoo
Pengasas, codencode Academy
📱 +601131652854
🌐 codencode.my
📍 Johor Bahru, Malaysia"""
    },

    # ── Tuition & Enrichment Centres (Partnership / Referral) ────────
    "en_referral": {
        "subjects": [
            "Quick partnership idea — Python & AI for your students",
            "Something that could work well for both of us",
            "Referral income idea for {school_name}",
            "Can we help each other out?",
        ],
        "body": """Hi {contact_name},

I came across {school_name} and thought there might be a natural fit here — so I'll just be direct.

I'm Sasha, I run codencode Academy in JB. We teach Python and AI online in English, Mandarin, and BM. Our students are mostly teens and young adults looking to build real tech skills.

I think your students and ours are probably pretty similar — and I'd love to explore a simple referral arrangement.

Here's how it works:
→ I come in and run a free 45-minute Python & AI demo for your students — no cost to you at all
→ If any of them want to continue, they sign up with us
→ You earn RM 50–100 for every student who enrols through you

No contracts. No complicated setup. Just a straightforward arrangement that benefits both of us.

I'm not asking you to commit to anything right now. Just wondering if it's worth a 10-minute chat to see if this makes sense.

Would a quick call this week work for you?

Cheers,
Sasha
codencode Academy | codencode.my
📱 +601131652854

P.S. Feel free to check us out at codencode.my first — I'd rather you know what you're partnering with before we talk."""
    },

    # ── Chinese Independent Schools (Mandarin) ────────────────────
    "cn_school": {
        "subjects": [
            "免费Python与AI体验课 — 为{school_name}学生提供",
            "想为贵校学生提供一堂免费的AI编程课",
            "关于与{school_name}合作的小提议",
        ],
        "body": """尊敬的{contact_name}，

您好！打扰了，我来简单介绍一下自己。

我叫Sasha Khoo，是codencode Academy的创办人。我们是柔佛新山第一所三语编程学院，以英语、普通话及马来语教授Python和人工智能课程。

我想为{school_name}的同学提供一堂免费的45分钟Python & AI体验课——可以在礼堂或教室进行，时间完全配合学校的安排。

这堂课里，同学们将会：
• 亲手写出真正的Python代码
• 亲眼看到AI实时响应
• 了解为什么这项技能对他们的未来非常重要

对贵校没有任何费用，也没有任何附带条件。

请问您是负责这类安排的合适人选吗？或者我应该联系其他老师？

期待您的回复，谢谢！

Sasha Khoo（许娜塔莎）
codencode Academy 创办人
📱 +601131652854
🌐 codencode.my
📍 柔佛新山 | Zoom线上授课"""
    },

    # ── Follow-up (if no reply after 5–7 days) ──────────────────────
    "en_followup": {
        "subjects": [
            "Just checking — did my last email land okay?",
            "Following up — re: free Python session for your students",
            "Still happy to help if the timing works",
        ],
        "body": """Hi {contact_name},

Just wanted to follow up on my last email — I know things get buried quickly.

I was offering a free 45-minute Python & AI session for your students at {school_name}, completely at no cost and no commitment required.

If the timing wasn't right before, I'm happy to work around whatever fits your school calendar — even a slot next term would be fine.

Just a one-line reply is all I need to know if this is something worth exploring.

Thanks for your time,
Sasha
codencode Academy | codencode.my
📱 +601131652854"""
    },
}

# ── CONTACT LIST ─────────────────────────────────────────────────
# Format: (school_name, contact_name, email, template_key)
contacts = [
    # ── JB — International & Private Schools ──
    ("REAL International School JB",     "Admissions Team",  "enquiry_jb@real.edu.my",               "en_school"),
    ("Stellar International School",     "Admissions",       "enquiry@stellar.edu.my",               "en_school"),
    ("Austin Heights Int'l School",      "Admissions",       "enquiry@austinheights.edu.my",         "en_school"),
    ("Excelsior International School",   "Admissions",       "info@excelsior.edu.my",                "en_school"),
    ("Paragon Private & Int'l School",   "Admissions",       "enquiry@paragon.edu.my",               "en_school"),
    ("Sri Ara International School",     "Admin Team",       "admin@sriara.edu.my",                  "en_school"),
    ("Raffles American School JB",       "Admissions",       "admissions@ras.edu.my",                "en_school"),

    # ── JB — Government Schools ──
    ("SMKA Johor Bahru",                 "Guru Kanan ICT",   "JRA1001@moe.edu.my",                   "bm_school"),

    # ── KL — International Schools ──
    ("AIS International School KL",      "Marketing Team",   "front.desk@ais-kl.edu.my",             "en_school"),
    ("Cempaka Int'l School Damansara",   "Admissions",       "admissions@cempaka.edu.my",            "en_school"),
    ("Alice Smith School",               "Enrichment Team",  "klass@alice-smith.edu.my",             "en_school"),
    ("ISKL",                             "Co-curriculum",    "iskl@iskl.edu.my",                     "en_school"),
    ("Mont'Kiara Int'l School",          "Admissions",       "mkis@mkis.edu.my",                     "en_school"),
    ("Sri KDU Kota Damansara",           "Admissions",       "admissions@srikdu.edu.my",             "en_school"),
    ("Sri KDU Subang Jaya",              "Admissions",       "admissions.sj@srikdu.edu.my",          "en_school"),
    ("Fairview Int'l School KL",         "Admissions",       "fiskl@fairview.edu.my",                "en_school"),
    ("Sunway Int'l School Subang",       "Admissions",       "sis@sunway.edu.my",                    "en_school"),
    ("UCSI Int'l School KL",             "Admissions",       "info@ucsiinternationalschool.edu.my",  "en_school"),
    ("MIGS Int'l School Ampang",         "Admissions",       "info@migs.edu.my",                     "en_school"),

]

# ── HELPERS ──────────────────────────────────────────────────────
def pick_subject(template_key, school_name):
    """Randomly pick a subject line variant and fill in school name."""
    subjects = TEMPLATES[template_key]["subjects"]
    chosen = random.choice(subjects)
    return chosen.format(school_name=school_name)

def build_message(template_key, school_name, contact_name):
    tmpl = TEMPLATES.get(template_key, TEMPLATES["en_school"])
    subject = pick_subject(template_key, school_name)
    body = tmpl["body"].format(
        school_name=school_name,
        contact_name=contact_name
    )
    return subject, body

def send_email(to_email, school_name, contact_name, template_key):
    subject, body = build_message(template_key, school_name, contact_name)

    msg = MIMEMultipart()
    msg['From']    = f"{SENDER_NAME} <{GMAIL_ADDRESS}>"
    msg['To']      = to_email
    msg['Subject'] = subject

    # Plain text body (more human — avoid HTML emails for cold outreach)
    msg.attach(MIMEText(body, 'plain', 'utf-8'))

    with smtplib.SMTP_SSL('smtp.gmail.com', 465) as server:
        server.login(GMAIL_ADDRESS, APP_PASSWORD)
        server.send_message(msg)

    return subject  # return for logging

def log_result(school, email, template, subject, status):
    with open(LOG_FILE, 'a', newline='', encoding='utf-8') as f:
        csv.writer(f).writerow([
            datetime.now().strftime('%Y-%m-%d %H:%M'),
            school, email, template, subject, status
        ])

def human_delay(base_seconds):
    """Add slight random variation to delay so emails don't look scheduled."""
    jitter = random.uniform(-8, 15)
    actual = max(20, base_seconds + jitter)
    return actual

# ── MAIN ─────────────────────────────────────────────────────────
if __name__ == "__main__":
    print("=" * 60)
    print("  codencode Academy — School Outreach Email Script v2")
    print("=" * 60)
    print(f"\n  From   : {SENDER_NAME} <{GMAIL_ADDRESS}>")
    print(f"  To     : {len(contacts)} contacts")
    print(f"  Delay  : ~{DELAY_SECONDS}s between emails (with random jitter)")
    print(f"  Log    : {LOG_FILE}")
    print()

    # Safety check
    if "your_email" in GMAIL_ADDRESS:
        print("❌  Update GMAIL_ADDRESS and APP_PASSWORD first!")
        exit(1)

    # Confirm before sending
    confirm = input(f"  Send to all {len(contacts)} contacts? Type YES to confirm: ")
    if confirm.strip() != "YES":
        print("  Cancelled.")
        exit(0)

    print()

    # CSV header
    with open(LOG_FILE, 'w', newline='', encoding='utf-8') as f:
        csv.writer(f).writerow([
            'Timestamp', 'School', 'Email', 'Template', 'Subject Used', 'Status'
        ])

    sent, failed = 0, 0

    for i, (school, contact, email, tmpl) in enumerate(contacts, 1):
        print(f"[{i}/{len(contacts)}] 📧  {school}")
        print(f"          To: {email}")

        try:
            subject_used = send_email(email, school, contact, tmpl)
            log_result(school, email, tmpl, subject_used, 'sent')
            sent += 1
            print(f"          ✅  Sent — Subject: \"{subject_used}\"")

            if i < len(contacts):
                delay = human_delay(DELAY_SECONDS)
                print(f"          ⏳  Waiting {delay:.0f}s before next...\n")
                time.sleep(delay)

        except Exception as e:
            print(f"          ❌  Failed: {e}\n")
            log_result(school, email, tmpl, "—", f'failed: {e}')
            failed += 1
            time.sleep(5)

    print()
    print("=" * 60)
    print(f"  ✅  Sent    : {sent}")
    print(f"  ❌  Failed  : {failed}")
    print(f"  📊  Log saved to: {LOG_FILE}")
    print("=" * 60)
    print()
    print("  Next steps:")
    print("  → Check sent_log.csv to see which subject lines were used")
    print("  → Follow up with non-replies after 5–7 days")
    print("  → Use the 'en_followup' template for follow-ups")
    print("  → WhatsApp the HIGH priority contacts manually too")