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

TEMPLATES = {

    # ── International & Private Schools (English) ──────────────────
    "en_school": {
        "subjects": [
            "Collaboration proposal for {school_name} — Python & AI for your students",
            "Quick question about your students and coding",
            "Can I visit {school_name} for 45 minutes?",
            "Something your students might actually enjoy",
        ],
        "body": """Hi {contact_name},

I'll keep this short — I know how full inboxes get.

My name is Sasha. I'm based in Johor Bahru and I run codencode Academy, a small coding school that teaches Python and AI in three languages — English, Mandarin, and Bahasa Melayu.

What I'm hoping to offer {school_name} is a free 45-minute session, in your auditorium or any classroom, where your students get to write real Python code and watch it talk to an AI — live, in front of them. No slides. No sales pitch. Just hands-on code.

The last school we visited had students asking to sign up before we even finished.

I'm not asking for anything today — just whether you'd be open to this kind of session. If yes, I'll work around your schedule completely.

Would you be the right person to talk to about this, or should I reach out to someone else?

Thanks for reading,
Sasha Khoo
Founder, codencode Academy
+60196811628
codencode.my
JB-based | Classes online via Zoom

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

Saya ingin memohon peluang untuk mengadakan sesi Python & AI percuma selama 45 minit untuk pelajar {school_name} — di dewan sekolah atau mana-mana bilik yang sesuai, pada masa yang senang untuk pihak sekolah.

Semasa sesi ini, pelajar akan:
- Menulis kod Python sebenar (bukan drag-and-drop)
- Melihat AI bertindak balas secara langsung di hadapan mereka
- Memahami mengapa kemahiran ini penting untuk masa depan mereka

Tiada kos . Saya hanya ingin memberi pelajar {school_name} pendedahan awal kepada kemahiran yang semakin dicari dalam pasaran kerja hari ini.

Adakah tuan/puan berminat untuk saya hubungi bagi mengaturkan perkara ini?

Sekian, terima kasih atas masa tuan/puan.

Sasha Khoo
Pengasas, codencode Academy
+60196811628
codencode.my
Johor Bahru, Malaysia"""
    },

    # ── Chinese Independent Schools (Mandarin) ────────────────────
    "cn_school": {
        "subjects": [
            "想为{school_name}同学提供一堂免费的Python & AI体验课",
            "关于为{school_name}学生开展AI编程公益课的建议",
            "免费Python与AI课堂体验 — 专为独中生设计，三语教学",
            "冒昧打扰 — 希望为{school_name}同学带来一堂AI编程体验课",
        ],
        "body": """尊敬的{contact_name}，

您好！冒昧打扰，请多包涵。

我叫Sasha Khoo，是codencode Academy的创办人。我们是柔佛新山第一所三语编程学院，以普通话、英语及马来语教授Python和人工智能课程。

身为华文教育体系培养出来的一分子，我深深明白独中生的努力与潜力。正因如此，我特别希望能为{school_name}的同学提供一堂免费的45分钟Python & AI体验课——在贵校礼堂或教室进行，时间完全配合学校的安排。

这堂课里，同学们将会：
- 亲手写出真正的Python代码（不是拖拉积木）
- 亲眼看到AI实时用三种语言回应
- 了解为什么这项技能对他们升学和就业都至关重要

对贵校没有任何费用，也没有任何附带条件。纯粹是希望让更多独中生有机会接触AI时代最重要的技能。

请问您是负责这类课外活动安排的合适人选吗？或者我应该联系哪位老师？

期待您的回复，谢谢！

Sasha Khoo（许娜塔莎）
codencode Academy 创办人
+60196811628
codencode.my
柔佛新山 | Zoom线上授课

附注：我们在Google上获得4.7星好评，欢迎参考。"""
    },

    # ── Follow-up English ──────────────────────────────────────────
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
+60196811628"""
    },

    # ── Follow-up Chinese ─────────────────────────────────────────
    "cn_followup": {
        "subjects": [
            "冒昧再次打扰 — 关于为{school_name}提供免费AI体验课",
            "跟进上次的邮件 — 如有需要随时联系",
        ],
        "body": """尊敬的{contact_name}，

您好，冒昧再次打扰。

之前我曾写信希望为{school_name}的同学提供一堂免费的Python & AI体验课，不知道邮件是否顺利送达？

若时机未到，完全没关系，我可以配合贵校的时间表，下学期或任何合适的时间都可以。

只需一行回复，告诉我是否有兴趣了解更多。

谢谢您的时间！

Sasha Khoo
codencode Academy
+60196811628 | codencode.my"""
    },
}

# ════════════════════════════════════════════════════════════════════
# CONTACT LIST — Format: (school_name, contact_name, email, template)
# ════════════════════════════════════════════════════════════════════

contacts = [

    # ──────────────────────────────────────────────────────────────
    # JB — INTERNATIONAL & PRIVATE SCHOOLS  (7 schools)
    # ──────────────────────────────────────────────────────────────
    ("REAL International School JB",     "Admissions Team", "enquiry_jb@real.edu.my",              "en_school"),
    ("Stellar International School",     "Admissions",      "enquiry@stellar.edu.my",              "en_school"),
    ("Austin Heights Int'l School",      "Admissions",      "enquiry@austinheights.edu.my",        "en_school"),
    ("Excelsior International School",   "Admissions",      "info@excelsior.edu.my",               "en_school"),
    ("Paragon Private & Int'l School",   "Admissions",      "enquiry@paragon.edu.my",              "en_school"),
    ("Sri Ara International School",     "Admin Team",      "admin@sriara.edu.my",                 "en_school"),
    ("Raffles American School JB",       "Admissions",      "admissions@ras.edu.my",               "en_school"),

    # ──────────────────────────────────────────────────────────────
    # JB — GOVERNMENT SCHOOLS / SMK  (8 confirmed MOE emails)
    # ──────────────────────────────────────────────────────────────
    ("SMKA Johor Bahru",                 "Guru Kanan ICT",  "JRA1001@moe.edu.my",                  "bm_school"),
    ("SMK Taman Johor Jaya 1",           "Guru Kanan ICT",  "JEA1045@moe.edu.my",                  "bm_school"),
    ("SMK Taman Desa Jaya",              "Guru Kanan ICT",  "JEA1057@moe.edu.my",                  "bm_school"),
    ("SMK Taman Desa Tebrau",            "Guru Kanan ICT",  "JEA1080@moe.edu.my",                  "bm_school"),
    ("SMK Taman Molek",                  "Guru Kanan ICT",  "JEA1067@moe.edu.my",                  "bm_school"),
    ("SMK Taman Tun Aminah Skudai",      "Guru Kanan ICT",  "jea1046@moe.edu.my",                  "bm_school"),
    ("SMK Taman Selesa Jaya Skudai",     "Guru Kanan ICT",  "jea1084@moe.edu.my",                  "bm_school"),
    ("SMK Taman Bukit Indah",            "Guru Kanan ICT",  "jea1087@moe.edu.my",                  "bm_school"),

    # ──────────────────────────────────────────────────────────────
    # JB — CHINESE INDEPENDENT SCHOOLS
    # 宽柔 Foon Yew — Malaysia's largest, 12,000 students, 3 campuses
    # ──────────────────────────────────────────────────────────────
    ("宽柔中学 Foon Yew JB 校本部",        "教务处",           "fyhs@foonyew.edu.my",                 "cn_school"),
    ("宽柔中学 Foon Yew 古来分校",         "教务处",           "enquiry@fyk.edu.my",                  "cn_school"),
    ("宽柔中学 Foon Yew 至达城分校",       "教务处",           "fysa@foonyewsa.edu.my",               "cn_school"),

    # ──────────────────────────────────────────────────────────────
    # KL — INTERNATIONAL SCHOOLS  (11 schools)
    # ──────────────────────────────────────────────────────────────
    ("AIS International School KL",      "Marketing Team",  "front.desk@ais-kl.edu.my",            "en_school"),
    ("Cempaka Int'l School Damansara",   "Admissions",      "admissions@cempaka.edu.my",           "en_school"),
    ("Alice Smith School KL",            "Enrichment Team", "klass@alice-smith.edu.my",            "en_school"),
    ("ISKL",                             "Co-curriculum",   "iskl@iskl.edu.my",                    "en_school"),
    ("Mont'Kiara Int'l School",          "Admissions",      "mkis@mkis.edu.my",                    "en_school"),
    ("Sri KDU Kota Damansara",           "Admissions",      "admissions@srikdu.edu.my",            "en_school"),
    ("Sri KDU Subang Jaya",              "Admissions",      "admissions.sj@srikdu.edu.my",         "en_school"),
    ("Fairview Int'l School KL",         "Admissions",      "fiskl@fairview.edu.my",               "en_school"),
    ("Sunway Int'l School Subang",       "Admissions",      "sis@sunway.edu.my",                   "en_school"),
    ("UCSI Int'l School KL Cheras",      "Admissions",      "info@ucsiinternationalschool.edu.my", "en_school"),
    ("MIGS Int'l School Ampang",         "Admissions",      "info@migs.edu.my",                    "en_school"),

    # ──────────────────────────────────────────────────────────────
    # KL — GOVERNMENT SCHOOLS
    # NOTE: Call first to confirm MOE email address before sending!
    #   SMK TTDI          03-7726 2522
    #   SMK Sri Aman PJ   03-7956 4312
    #   SMK Bandar Sunway 03-5631 7773
    # Replace placeholder emails below with confirmed addresses.
    # ──────────────────────────────────────────────────────────────
    # ("SMK Taman Tun Dr Ismail TTDI",  "Guru Kanan ICT",  "CONFIRMED_EMAIL@moe.edu.my",  "bm_school"),
    # ("SMK (P) Sri Aman PJ",           "Guru Kanan ICT",  "CONFIRMED_EMAIL@moe.edu.my",  "bm_school"),
    # ("SMK Bandar Sunway",             "Guru Kanan ICT",  "CONFIRMED_EMAIL@moe.edu.my",  "bm_school"),

    # ──────────────────────────────────────────────────────────────
    # KL / KV — CHINESE INDEPENDENT SCHOOLS  (3 schools)
    # ──────────────────────────────────────────────────────────────
    ("坤成中学 Kuen Cheng High School KL", "教务处",          "info@kuencheng.edu.my",               "cn_school"),
    ("中华独立中学 Chong Hwa KL",           "教务处",          "info@chonghwakl.edu.my",              "cn_school"),
    ("巴生中华独立中学 Klang Chung Hwa",    "教务处",          "chhsklang@chunghuaklang.edu.my",      "cn_school"),

]


# ── HELPERS ──────────────────────────────────────────────────────

def pick_subject(template_key, school_name):
    subjects = TEMPLATES[template_key]["subjects"]
    return random.choice(subjects).format(school_name=school_name)

def build_message(template_key, school_name, contact_name):
    tmpl = TEMPLATES.get(template_key, TEMPLATES["en_school"])
    subject = pick_subject(template_key, school_name)
    body = tmpl["body"].format(school_name=school_name, contact_name=contact_name)
    return subject, body

def send_email(to_email, school_name, contact_name, template_key):
    subject, body = build_message(template_key, school_name, contact_name)
    msg = MIMEMultipart()
    msg['From']    = f"{SENDER_NAME} <{GMAIL_ADDRESS}>"
    msg['To']      = to_email
    msg['Subject'] = subject
    msg.attach(MIMEText(body, 'plain', 'utf-8'))
    with smtplib.SMTP_SSL('smtp.gmail.com', 465) as server:
        server.login(GMAIL_ADDRESS, APP_PASSWORD)
        server.send_message(msg)
    return subject

def log_result(school, email, template, subject, status):
    with open(LOG_FILE, 'a', newline='', encoding='utf-8') as f:
        csv.writer(f).writerow([
            datetime.now().strftime('%Y-%m-%d %H:%M'),
            school, email, template, subject, status
        ])

def human_delay(base):
    return max(20, base + random.uniform(-8, 15))

def print_summary(batch):
    en = sum(1 for c in batch if c[3] == "en_school")
    bm = sum(1 for c in batch if c[3] == "bm_school")
    cn = sum(1 for c in batch if c[3] == "cn_school")
    print(f"\n  Breakdown:")
    print(f"  GB  International schools (EN) : {en}")
    print(f"  MY  Government schools (BM)    : {bm}")
    print(f"  CN  Chinese ind. schools (ZH)  : {cn}")
    print(f"  -   TOTAL                      : {len(batch)}\n")


# ── MAIN ─────────────────────────────────────────────────────────

if __name__ == "__main__":
    print("=" * 60)
    print("  codencode Academy — School Outreach Email Script v3")
    print("=" * 60)
    print(f"\n  From  : {SENDER_NAME} <{GMAIL_ADDRESS}>")
    print(f"  Delay : ~{DELAY_SECONDS}s between emails (with jitter)")
    print(f"  Log   : {LOG_FILE}")

    if "your_email" in GMAIL_ADDRESS:
        print("\n  ERROR: Update GMAIL_ADDRESS and APP_PASSWORD first!")
        exit(1)

    # ── Batch selector ──────────────────────────────────────────
    print("\n  Which schools do you want to send to?")
    print("  [1] ALL contacts (JB + KL, all languages)")
    print("  [2] JB schools only")
    print("  [3] KL / Klang Valley only")
    print("  [4] Chinese independent schools only")
    print("  [5] Government schools (BM) only")
    print("  [6] International schools (EN) only")
    choice = input("\n  Enter choice [1-6]: ").strip()

    if choice == "2":
        batch = [c for c in contacts if any(x in c[0] for x in [
            "REAL","Stellar","Austin","Excelsior","Paragon","Sri Ara","Raffles",
            "SMKA","SMK Taman","宽柔"
        ])]
    elif choice == "3":
        batch = [c for c in contacts if any(x in c[0] for x in [
            "KL","Cempaka","Alice","ISKL","Mont","Sri KDU","Fairview","Sunway",
            "UCSI","MIGS","TTDI","Sri Aman","Bandar Sunway","坤成","中华","巴生"
        ])]
    elif choice == "4":
        batch = [c for c in contacts if c[3] == "cn_school"]
    elif choice == "5":
        batch = [c for c in contacts if c[3] == "bm_school"]
    elif choice == "6":
        batch = [c for c in contacts if c[3] == "en_school"]
    else:
        batch = contacts

    print_summary(batch)

    confirm = input(f"  Send to all {len(batch)} contacts? Type YES to confirm: ")
    if confirm.strip() != "YES":
        print("  Cancelled.")
        exit(0)

    print()

    # Write CSV header
    with open(LOG_FILE, 'w', newline='', encoding='utf-8') as f:
        csv.writer(f).writerow([
            'Timestamp', 'School', 'Email', 'Template', 'Subject Used', 'Status'
        ])

    sent, failed = 0, 0
    lang_icon = {"en_school": "[EN]", "bm_school": "[BM]", "cn_school": "[ZH]"}

    for i, (school, contact, email, tmpl) in enumerate(batch, 1):
        icon = lang_icon.get(tmpl, "[--]")
        print(f"[{i}/{len(batch)}] {icon}  {school}")
        print(f"           To : {email}")

        try:
            subject_used = send_email(email, school, contact, tmpl)
            log_result(school, email, tmpl, subject_used, 'sent')
            sent += 1
            print(f"           OK   Sent")
            print(f"           Subj: {subject_used}")
            if i < len(batch):
                delay = human_delay(DELAY_SECONDS)
                print(f"           Waiting {delay:.0f}s...\n")
                time.sleep(delay)
        except Exception as e:
            print(f"           FAIL: {e}\n")
            log_result(school, email, tmpl, "—", f'failed: {e}')
            failed += 1
            time.sleep(5)

    print()
    print("=" * 60)
    print(f"  Sent   : {sent}")
    print(f"  Failed : {failed}")
    print(f"  Log    : {LOG_FILE}")
    print("=" * 60)
    print()
    print("  Reminders:")
    print("  -> Check sent_log.csv for subject lines used")
    print("  -> Follow up non-replies after 5-7 days")
    print("  -> For KL gov schools, call first to get MOE email:")
    print("     SMK TTDI          03-7726 2522")
    print("     SMK Sri Aman PJ   03-7956 4312")
    print("     SMK Bandar Sunway 03-5631 7773")
    print("  -> Uncomment those 3 lines in contacts[] once confirmed")