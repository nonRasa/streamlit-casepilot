# GH9218 — exact live case and answer

Run date: 2026-10-10. Source: `eval/cases.json`, development split, `no_dense`, `gpt-4.1-mini`.

The ticket input below is the exact `initial_message` passed to the agent. `initial_facts` was `{}` and `initial_checks` was `[]`.

## Exact ticket input

``````text
file_uploader with large file results in server getting killed

### Checklist

- [X] I have searched the [existing issues](https://github.com/streamlit/streamlit/issues) for similar issues.
- [X] I added a very descriptive title to this issue.
- [X] I have provided sufficient information below to help reproduce this issue.

### Summary

I am using st.file_uploader to upload ~3.5gb file into my streamlit dashboard. This however, results in the server getting killed.
When I inspect using btop, Upon file upload, the server starts using an astronomic amount of RAM.

EDIT: I tried imposing a RAM limit by dockerizing the dashboard and settting a 4gb RAM limit, but it just gets killed in the container.

### Reproducible Code Example

```Python
import streamlit as st

uploaded_file = st.file_uploader("Choose a video file", type=["mp4", "mov", "avi"])
```


### Steps To Reproduce

streamlit run dashboard.py --maxUploadSize=5000

### Expected Behavior

It's probably better to stream it in chunks to disk when clicking an 'upload file' button.

### Current Behavior

The server gets killed.

### Is this a regression?

- [ ] Yes, this used to work in a previous version.

### Debug info

- Streamlit version:
- Python version:
- Operating System:
- Browser:


### Additional Information

_No response_
``````

## Exact final response returned by the system

``````text
پاسخ پیشنهادی: اقدام: فقط نسخهٔ دقیق Streamlit در محیطی که خطا رخ می‌دهد از گزارش‌دهنده خواسته شود؛ این داده برای سنجش سازگاری شاهد لازم است. علت یا رفع مشکل هنوز تأیید نشده است.

محدودیت: پاسخ پیشنهادی از کنترل ساختار یا استناد عبور نکرد. کد خطا: `judge_rejected`.

وضعیت: رفع مشکل تأیید نشده است؛ ثبت پاسخ فقط پس از تأیید نگه‌دارنده انجام می‌شود.

ارجاع: خلاصهٔ قابل بررسی برای نگه‌دارنده.

مسئلهٔ گزارش‌شده:

````text
file_uploader with large file results in server getting killed

### Checklist

- [X] I have searched the [existing issues](https://github.com/streamlit/streamlit/issues) for similar issues.
- [X] I added a very descriptive title to this issue.
- [X] I have provided sufficient information below to help reproduce this issue.

### Summary

I am using st.file_uploader to upload ~3.5gb file into my streamlit dashboard. This however, results in the server getting killed.
When I inspect using btop, Upon file upload, the server starts using an astronomic amount of RAM.

EDIT: I tried imposing a RAM limit by dockerizing the dashboard and settting a 4gb RAM limit, but it just gets killed in the container.

### Reproducible Code Example

```Python
import streamlit as st

uploaded_file = st.file_uploader("Choose a video file", type=["mp4", "mov", "avi"])
```


### Steps To Reproduce

streamlit run dashboard.py --maxUploadSize=5000

### Expected Behavior

It's probably better to stream it in chunks to disk when clicking an 'upload file' button.

### Current Behavior

The server gets killed.

### Is this a regression?

- [ ] Yes, this used to work in a previous version.

### Debug info

- Streamlit version:
- Python version:
- Operating System:
- Browser:


### Additional Information

_No response_
````

محیط گزارش‌شده:

```text
نامعلوم
```

بررسی‌ها: آزمایش ساخت‌یافتهٔ انجام‌شده ثبت نشده است.

اقدام‌های نقل‌شده از گزارش کاربر (اجرا و نتیجه مستقلاً تأیید نشده):

```text
- EDIT: I tried imposing a RAM limit by dockerizing the dashboard and settting a 4gb RAM limit, but it just gets killed in the container.
```

مجهولات:

```text
streamlit_version, python_version, deployment, reproducible
```

شواهد: شاهد فنی پذیرفته‌شده در این نوبت موجود نیست.

اقدام: فقط نسخهٔ دقیق Streamlit در محیطی که خطا رخ می‌دهد از گزارش‌دهنده خواسته شود؛ این داده برای سنجش سازگاری شاهد لازم است. علت یا رفع مشکل هنوز تأیید نشده است.

محدودیت: علت و رفع مشکل مستقلاً تأیید نشده‌اند.

محدودیت: کد توقف `judge_rejected`؛ خطای داخلی ضرورت ارجاع پرونده را اثبات نمی‌کند.
``````

## Reviewed model draft

This draft was **not** the final answer. The judge rejected it after one repair. Exact fields from `reviewed_draft.units`:

### question

``````text
لطفاً نسخه استریم‌لیت، نسخه پایتون و اطلاعات سیستم عامل خود را ارائه دهید. آیا در محیط با نسخه‌های مختلف یا تنظیمات حافظه متفاوت این مشکل بازتولید می‌شود؟
``````

### next_step

``````text
لطفاً نسخه‌های دقیق `streamlit` و `python` و نسخه و نوع سیستم عامل را ارائه دهید تا تفاوت‌های محیط بررسی شود.
``````

### rationale

``````text
شناخته شده است که `st.file_uploader` داده‌های فایل را در حافظه RAM نگهداری می‌کند و پس از بازخوانی برنامه (re-run) پاک می‌شود. استفاده از فایل‌های حجیم ممکن است باعث مصرف زیاد RAM شود که در گزارش ذکر شده است سرور در حین بارگذاری فایل ~3.5 گیگابایتی کشته می‌شود. نبود اطلاعات نسخه‌ها و محیط اجرای برنامه مانع از تأیید دلیل دقیق شده است، لذا بررسی نسخه‌ها و محیط اجرا برای شناسایی علت ضروری است.
``````

### hypotheses.0

``````text
حافظه مصرفی بالا و کش شدن داده‌ها ممکن است باعث مصرف بیش از حد RAM و موجب خاموش شدن سرور شده باشد.
``````

## Run record

- Decision: `escalate`; final generation: `recovery_fallback`; validation error: `judge_rejected`.
- Model requests: 6; added estimated cost: $0.01396384; added uncertain reservation: $0.00000000.
- Shared ledger charged or reserved after run: $0.16612816 of $0.30.
- Local raw answer SHA-256: `28ffc8e2a9fbfccb2d80d399192a5f5254efd0cf358d71f8b222a2d0a2d9f751`.
- Raw response and cache remain local; no credential or private cache is published.
