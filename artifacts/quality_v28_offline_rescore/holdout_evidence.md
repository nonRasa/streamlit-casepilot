# پیوست متن دقیق و مسیر انتساب علت

این پیوست استخراج آفلاین از آثار تاریخی است؛ گزاره‌های داور، تأیید مستقل محسوب نمی‌شوند.

## H1_A

Artifact: `artifacts\quality_v28_remaining\turns\holdout_r0_H1_A.json`

### پیش‌نویس 0

Draft: `9539619e0827e86b5553af95aa962a986606f233d5544f8353612a7c3d8e5f9d`

J = `$.requests[4].payload.messages[1].content (JSON)`

`J.draft.units[0].text` — `next_step` — `u_5e2263d53cb19621d7bf2077`

```text
طراحی قابلیت ذخیره و بازیابی دیدهای فیلترشده و مرتب‌شده را بررسی و با تیم تصمیم‌گیری فنی مطرح کنید.
```

`J.draft.units[1].text` — `rationale` — `u_d9dd7f4cd8cff1d8d0d65627`

```text
هدف: درخواست روشن کاربر برای تصمیم طراحی نگه‌دارنده آماده می‌شود؛ جزئیات رفتار و شرط پذیرش در پیشنهاد آمده‌اند.
```

`J.draft.units[2].text` — `feature_proposal.acceptance_condition` — `u_b3941eb140c647f69a513866`

```text
بازگشایی یک دید ذخیره شده فیلترها و ترتیب آن را بازیابی کند؛ حذف دید هیچ گزارشی را تغییر ندهد.
```

`J.draft.units[3].text` — `feature_proposal.constraints` — `u_618a0ec335f9b44ea875bc76`

```text
دید ذخیره شده باید فقط برای بازبین مربوطه خصوصی باشد و امکان تغییر نام یا حذف آن وجود داشته باشد.
```

`J.draft.units[4].text` — `feature_proposal.current_behavior` — `u_97d457e77ac12c2357dc83a8`

```text
نامعلوم: این مشخصه هنوز در پیشنهاد اعتبارسنجی نشده؛ نگه‌دارنده آن را تعیین کند.
```

`J.draft.units[5].text` — `feature_proposal.desired_behavior` — `u_cc15ca32cd1444978ba14834`

```text
امکان ذخیره و بازیابی دیدهای نام‌دار در صف گزارش‌های ساخت فراهم شود. یک دید ذخیره شده فیلترهای وضعیت انتخابی و ترتیب مرتب‌سازی را می‌تواند ذخیره کند. این دید خصوصی برای بازبین باشد و بتوان آن را تغییر نام داد یا حذف کرد بدون آنکه گزارش‌های اصلی تغییری کنند.
```

`J.draft.units[6].text` — `feature_proposal.user_need` — `u_1628d8db4ecd3075f6f84ef4`

```text
درخواست: نیاز است بازبین‌ها قادر باشند دیدهای نام‌داری از صف گزارش‌های ساخت ذخیره و بازیابی کنند که شامل فیلترها و ترتیب مرتب‌سازی باشد.
```

`J.draft.units[7].text` — `feature_proposal.report_quotes.0` — `u_85c7fc1859420214f3f0d52a`

```text
Feature request: Let reviewers save named views of the build-report queue. A saved view can hold selected status filters and a sort order. It is private to the reviewer, can be renamed or deleted, and must not change the underlying reports. Acceptance: reopening a saved view restores its filters and order; deleting the view leaves every report unchanged. This is a new design request, not a statement about current capabilities.
```

رأی خام از `$.requests[4].raw_reply`: `escalate`؛ رأی نگهبان: `escalate`.

یافته‌های نگهبان برای همین draft:

```json
[
  {
    "criterion": "claim_support",
    "reason": "معنا: برچسب اختیاری نمی‌تواند عبارت فنیِ کشف‌شده از متن را به رویه تبدیل کند.",
    "unit_id": "u_5e2263d53cb19621d7bf2077"
  },
  {
    "criterion": "claim_support",
    "reason": "معنا: هر عبارت فنیِ کشف‌شده باید با شاهد منتخب مستقیم پشتیبانی شود.",
    "unit_id": "u_5e2263d53cb19621d7bf2077"
  },
  {
    "criterion": "claim_support",
    "reason": "شاهد: ادعای فنی یا پیش‌فرض پشتوانهٔ مستقیم ندارد.",
    "unit_id": "u_5e2263d53cb19621d7bf2077"
  },
  {
    "criterion": "claim_support",
    "reason": "شاهد: انتساب به کاربر شاهد مستقیم ندارد.",
    "unit_id": "u_d9dd7f4cd8cff1d8d0d65627"
  }
]
```

شواهد منتخب از `J.citations`:

```json
[]
```

### پیش‌نویس 1

Draft: `b175b2013298c3e2798a98821d124da49b37adb2cfac35cdd0b730216d4e7586`

J = `$.requests[5].payload.messages[1].content (JSON)`

`J.draft.units[0].text` — `next_step` — `u_65e89203f5c18169fefeef56`

```text
اقدام: نگه‌دارنده دربارهٔ افزودن رفتار درخواستی تصمیم طراحی بگیرد و شرط پذیرش پیشنهادی را بازبینی کند.
```

`J.draft.units[1].text` — `rationale` — `u_ca80f04dd3cd549493f82bdc`

```text
محدودیت: پیشنهاد شرح درخواست کاربر است؛ وجود رابط، علت یا امکان‌پذیری فنی تأیید نشده است.
```

`J.draft.units[2].text` — `feature_proposal.acceptance_condition` — `u_81b81204558c7717febf99ab`

```text
بازگشایی یک دید ذخیره شده فیلترها و ترتیب آن را بازیابی کند؛ حذف دید هیچ گزارشی را تغییر ندهد.
```

`J.draft.units[3].text` — `feature_proposal.constraints` — `u_a44e8d0193d1144629731eb6`

```text
دید ذخیره شده باید فقط برای بازبین مربوطه خصوصی باشد و امکان تغییر نام یا حذف آن وجود داشته باشد.
```

`J.draft.units[4].text` — `feature_proposal.current_behavior` — `u_18185232680516b92301fc11`

```text
نامعلوم: این مشخصه هنوز در پیشنهاد اعتبارسنجی نشده؛ نگه‌دارنده آن را تعیین کند.
```

`J.draft.units[5].text` — `feature_proposal.desired_behavior` — `u_c069684058152b8dd5c0ee1b`

```text
امکان ذخیره و بازیابی دیدهای نام‌دار در صف گزارش‌های ساخت فراهم شود. یک دید ذخیره شده فیلترهای وضعیت انتخابی و ترتیب مرتب‌سازی را می‌تواند ذخیره کند. این دید خصوصی برای بازبین باشد و بتوان آن را تغییر نام داد یا حذف کرد بدون آنکه گزارش‌های اصلی تغییری کنند.
```

`J.draft.units[6].text` — `feature_proposal.user_need` — `u_821d4fc5b66142e32a3eac0c`

```text
درخواست: نیاز است بازبین‌ها قادر باشند دیدهای نام‌داری از صف گزارش‌های ساخت ذخیره و بازیابی کنند که شامل فیلترها و ترتیب مرتب‌سازی باشد.
```

`J.draft.units[7].text` — `feature_proposal.report_quotes.0` — `u_a9a95c42dad582f1cd6ad5fb`

```text
Feature request: Let reviewers save named views of the build-report queue. A saved view can hold selected status filters and a sort order. It is private to the reviewer, can be renamed or deleted, and must not change the underlying reports. Acceptance: reopening a saved view restores its filters and order; deleting the view leaves every report unchanged. This is a new design request, not a statement about current capabilities.
```

رأی خام از `$.requests[5].raw_reply`: `escalate`؛ رأی نگهبان: `escalate`.

یافته‌های نگهبان برای همین draft:

```json
[
  {
    "criterion": "claim_support",
    "unit_id": "u_ca80f04dd3cd549493f82bdc",
    "reason": "معنا: معنای این واحد نامعلوم است و قابل پذیرش قطعی نیست."
  },
  {
    "criterion": "claim_support",
    "unit_id": "u_ca80f04dd3cd549493f82bdc",
    "reason": "شاهد: انتساب به کاربر شاهد مستقیم ندارد."
  }
]
```

شواهد منتخب از `J.citations`:

```json
[]
```

## H1_B

Artifact: `artifacts\quality_v28_remaining\turns\holdout_r0_H1_B.json`

### پیش‌نویس 0

Draft: `ebddb97bace35cd6364777b071207b186e9a40323160b6b6e4b9bea89d45c136`

J = `$.requests[4].payload.messages[1].content (JSON)`

`J.draft.units[0].text` — `next_step` — `u_0bd669f696058b11badb5f30`

```text
این درخواست ویژگی را به تیم نگه‌داری گزارش دهید تا درباره طراحی نهایی و پیاده‌سازی تصمیم بگیرند.
```

`J.draft.units[1].text` — `rationale` — `u_0ed4f35edb0a7dfd5ac0a97e`

```text
هدف: درخواست روشن کاربر برای تصمیم طراحی نگه‌دارنده آماده می‌شود؛ جزئیات رفتار و شرط پذیرش در پیشنهاد آمده‌اند.
```

`J.draft.units[2].text` — `feature_proposal.acceptance_condition` — `u_a8e420923c6860de3edf9302`

```text
بازگشایی یک دید ذخیره شده فیلترها و ترتیب آن را بازیابی کند؛ حذف دید هیچ گزارشی را تغییر ندهد.
```

`J.draft.units[3].text` — `feature_proposal.constraints` — `u_44a9e34bbdfcfe2df380b73f`

```text
دیدهای ذخیره شده خصوصی برای بازبین هستند و نباید گزارش‌های زیرساخت را تغییر دهند.
```

`J.draft.units[4].text` — `feature_proposal.current_behavior` — `u_45b96ad0280b8a530ae6bec4`

```text
نامعلوم: این مشخصه هنوز در پیشنهاد اعتبارسنجی نشده؛ نگه‌دارنده آن را تعیین کند.
```

`J.draft.units[5].text` — `feature_proposal.desired_behavior` — `u_0077bdbd4f539ec2c0851228`

```text
به بازبینان اجازه داده شود تا دیدهای نام‌گذاری شده از صف گزارش ساخت ذخیره و بازیابی کنند؛ این دیدها شامل فیلترهای وضعیت انتخاب شده و ترتیب مرتب‌سازی باشند و قابلیت تغییر نام یا حذف داشته باشند.
```

`J.draft.units[6].text` — `feature_proposal.user_need` — `u_773b559832fa4b9a6da9b1d2`

```text
درخواست: ذخیره و بازیابی دیدهای نام‌گذاری شده با فیلترها و ترتیب مرتب‌سازی در صف گزارش ساخت.
```

`J.draft.units[7].text` — `feature_proposal.report_quotes.0` — `u_1748d36b0f51a5bc5fec35dc`

```text
Feature request: Let reviewers save named views of the build-report queue. A saved view can hold selected status filters and a sort order. It is private to the reviewer, can be renamed or deleted, and must not change the underlying reports. Acceptance: reopening a saved view restores its filters and order; deleting the view leaves every report unchanged. This is a new design request, not a statement about current capabilities.
```

رأی خام از `$.requests[4].raw_reply`: `escalate`؛ رأی نگهبان: `escalate`.

یافته‌های نگهبان برای همین draft:

```json
[
  {
    "criterion": "claim_support",
    "unit_id": "u_a8e420923c6860de3edf9302",
    "reason": "شاهد: انتساب به کاربر شاهد مستقیم ندارد."
  },
  {
    "criterion": "claim_support",
    "unit_id": "u_44a9e34bbdfcfe2df380b73f",
    "reason": "شاهد: انتساب به کاربر شاهد مستقیم ندارد."
  },
  {
    "criterion": "claim_support",
    "unit_id": "u_0077bdbd4f539ec2c0851228",
    "reason": "شاهد: انتساب به کاربر شاهد مستقیم ندارد."
  },
  {
    "criterion": "claim_support",
    "unit_id": "u_773b559832fa4b9a6da9b1d2",
    "reason": "شاهد: انتساب به کاربر شاهد مستقیم ندارد."
  },
  {
    "criterion": "claim_support",
    "unit_id": "u_1748d36b0f51a5bc5fec35dc",
    "reason": "شاهد: انتساب به کاربر شاهد مستقیم ندارد."
  }
]
```

شواهد منتخب از `J.citations`:

```json
[]
```

## H2_A

Artifact: `artifacts\quality_v28_remaining\turns\holdout_r0_H2_A.json`

### پیش‌نویس 0

Draft: `233fce4cc30195ceda946a47d5d73e7a851183fb405ca896862432ae2e6c7273`

J = `$.requests[4].payload.messages[1].content (JSON)`

`J.draft.units[0].text` — `question` — `u_c24536f97ce2056e1cbe21c1`

```text
آیا می‌توانید یک مشاهده جدید ارائه دهید که زمان دقیق طول عمر اعلان toast را نسبت به زمان شروع rerun صفحه جدا کند؟
```

`J.draft.units[1].text` — `next_step` — `u_d86fd29794ee8ce2e2bb16b5`

```text
لطفاً یک مشاهده جدید ارائه دهید که زمان دقیق طول عمر اعلان toast را نسبت به زمان شروع rerun صفحه جدا کند تا بتوان تفاوت زمان‌بندی آن‌ها را تحلیل نمود.
```

`J.draft.units[2].text` — `rationale` — `u_4b4295cfecb27253c886517e`

```text
داشتن یک مشاهده دقیق از زمان‌بندی نمایش و ناپدید شدن اعلان toast نسبت به زمان شروع rerun به تشخیص اینکه آیا ناپدید شدن اعلان به علت شروع rerun است کمک می‌کند و امکان تفکیک دو زمان‌بندی را فراهم می‌آورد.
```

`J.draft.units[3].text` — `diagnostic.action` — `u_67a6ded811a92e78fbaa0102`

```text
Measure and log the precise timestamps of the `st.toast` notice appearing and disappearing, and separately log the timestamp when `st.rerun()` begins to execute.
```

`J.draft.units[4].text` — `diagnostic.missing_fact` — `u_eadbac3a0991fe86a6b082a9`

```text
یک مشاهده تجربی که زمان دقیق طول عمر اعلان را نسبت به زمان‌بندی rerun صفحه جدا کند.
```

رأی خام از `$.requests[4].raw_reply`: `accept`؛ رأی نگهبان: `repair`.

یافته‌های نگهبان برای همین draft:

```json
[
  {
    "criterion": "claim_support",
    "reason": "معنا: برچسب اختیاری نمی‌تواند عبارت فنیِ کشف‌شده از متن را به رویه تبدیل کند.",
    "unit_id": "u_d86fd29794ee8ce2e2bb16b5"
  },
  {
    "criterion": "claim_support",
    "reason": "معنا: هر عبارت فنیِ کشف‌شده باید با شاهد منتخب مستقیم پشتیبانی شود.",
    "unit_id": "u_d86fd29794ee8ce2e2bb16b5"
  },
  {
    "criterion": "claim_support",
    "reason": "معنا: برچسب اختیاری نمی‌تواند عبارت فنیِ کشف‌شده از متن را به رویه تبدیل کند.",
    "unit_id": "u_4b4295cfecb27253c886517e"
  },
  {
    "criterion": "claim_support",
    "reason": "معنا: هر عبارت فنیِ کشف‌شده باید با شاهد منتخب مستقیم پشتیبانی شود.",
    "unit_id": "u_4b4295cfecb27253c886517e"
  },
  {
    "criterion": "claim_support",
    "reason": "معنا: ادعای فنی باید عبارت دقیق داشته باشد.",
    "unit_id": "u_67a6ded811a92e78fbaa0102"
  },
  {
    "criterion": "claim_support",
    "reason": "معنا: هر عبارت فنیِ کشف‌شده باید با شاهد منتخب مستقیم پشتیبانی شود.",
    "unit_id": "u_eadbac3a0991fe86a6b082a9"
  },
  {
    "criterion": "claim_support",
    "reason": "شاهد: ادعای فنی یا پیش‌فرض پشتوانهٔ مستقیم ندارد.",
    "unit_id": "u_d86fd29794ee8ce2e2bb16b5"
  },
  {
    "criterion": "claim_support",
    "reason": "شاهد: ادعای فنی یا پیش‌فرض پشتوانهٔ مستقیم ندارد.",
    "unit_id": "u_4b4295cfecb27253c886517e"
  },
  {
    "criterion": "claim_support",
    "reason": "شاهد: ادعای فنی یا پیش‌فرض پشتوانهٔ مستقیم ندارد.",
    "unit_id": "u_eadbac3a0991fe86a6b082a9"
  }
]
```

شواهد منتخب از `J.citations`:

```json
[]
```

### پیش‌نویس 1

Draft: `035338fc25c47792629156670f89e4ed43538537cfe6184efc1f1eb19d6f2408`

J = `$.requests[6].payload.messages[1].content (JSON)`

`J.draft.units[0].text` — `question` — `u_a23c118fb5038ef7ab87161e`

```text
آیا می‌توانید یک مشاهده ثبت‌شده دقیق ارائه دهید که زمان شروع و پایان اعلام `st.toast` را نسبت به زمان شروع rerun صفحه در همان اجرا جدا کند؟.
```

`J.draft.units[1].text` — `next_step` — `u_6491f27f87951f96b124848a`

```text
لطفاً یک مشاهده جدید از زمان‌بندی دقیق طول عمر اعلان `st.toast` نسبت به زمان‌بندی شروع عملیات rerun صفحه ثبت کنید تا بتوان تفکیک زمان‌بندی این دو را بررسی نمود.
```

`J.draft.units[2].text` — `rationale` — `u_da6e158fb8116a621e0f2cf5`

```text
داشتن یک مشاهده دقیق از زمان‌بندی نمایش و ناپدید شدن اعلان toast نسبت به زمان شروع rerun به تفکیک و تحلیل علت ناپدید شدن زودهنگام کمک می‌کند.
```

`J.draft.units[3].text` — `diagnostic.action` — `u_3f32947603a126ae2c4a09d2`

```text
ثبت زمان دقیق شروع و پایان نمایش اعلان toast و مقایسه آن با زمان شروع rerun صفحه در همان اجرا.
```

`J.draft.units[4].text` — `diagnostic.missing_fact` — `u_7a472c2c9af37fdd12ddf2cf`

```text
یک مشاهده دقیق که زمان‌بندی کامل نمایش و ناپدید شدن اعلان toast را نسبت به زمان شروع rerun صفحه نشان دهد.
```

`J.draft.units[5].text` — `claims.0.quote` — `u_7baa9f8174fcc68b5122c4a8`

```text
1. Text is updated in string
2. Button is pressed and rerun occurs (but the the text was never rendered. Widget is reset
3. Widget reverts back to default
محدودیت: نسخهٔ محصول منبع نامعلوم است؛ انطباق با محیط شما تأیید نشده است.
```

رأی خام از `$.requests[6].raw_reply`: `accept`؛ رأی نگهبان: `repair`.

یافته‌های نگهبان برای همین draft:

```json
[
  {
    "criterion": "claim_support",
    "reason": "پرسش روی مشاهده جدید تاکید دارد، شواهد کافی نیست."
  },
  {
    "criterion": "claim_support",
    "unit_id": "u_a23c118fb5038ef7ab87161e",
    "reason": "معنا: برچسب اختیاری نمی‌تواند عبارت فنیِ کشف‌شده از متن را به رویه تبدیل کند."
  },
  {
    "criterion": "claim_support",
    "unit_id": "u_a23c118fb5038ef7ab87161e",
    "reason": "معنا: هر عبارت فنیِ کشف‌شده باید با شاهد منتخب مستقیم پشتیبانی شود."
  },
  {
    "criterion": "claim_support",
    "unit_id": "u_6491f27f87951f96b124848a",
    "reason": "معنا: برچسب اختیاری نمی‌تواند عبارت فنیِ کشف‌شده از متن را به رویه تبدیل کند."
  },
  {
    "criterion": "claim_support",
    "unit_id": "u_6491f27f87951f96b124848a",
    "reason": "معنا: هر عبارت فنیِ کشف‌شده باید با شاهد منتخب مستقیم پشتیبانی شود."
  },
  {
    "criterion": "claim_support",
    "unit_id": "u_da6e158fb8116a621e0f2cf5",
    "reason": "معنا: برچسب اختیاری نمی‌تواند عبارت فنیِ کشف‌شده از متن را به رویه تبدیل کند."
  },
  {
    "criterion": "claim_support",
    "unit_id": "u_da6e158fb8116a621e0f2cf5",
    "reason": "معنا: هر عبارت فنیِ کشف‌شده باید با شاهد منتخب مستقیم پشتیبانی شود."
  },
  {
    "criterion": "claim_support",
    "unit_id": "u_7a472c2c9af37fdd12ddf2cf",
    "reason": "معنا: برچسب اختیاری نمی‌تواند عبارت فنیِ کشف‌شده از متن را به رویه تبدیل کند."
  },
  {
    "criterion": "claim_support",
    "unit_id": "u_7a472c2c9af37fdd12ddf2cf",
    "reason": "معنا: هر عبارت فنیِ کشف‌شده باید با شاهد منتخب مستقیم پشتیبانی شود."
  },
  {
    "criterion": "claim_support",
    "unit_id": "u_a23c118fb5038ef7ab87161e",
    "reason": "شاهد: ادعای فنی یا پیش‌فرض پشتوانهٔ مستقیم ندارد."
  },
  {
    "criterion": "claim_support",
    "unit_id": "u_6491f27f87951f96b124848a",
    "reason": "شاهد: ادعای فنی یا پیش‌فرض پشتوانهٔ مستقیم ندارد."
  },
  {
    "criterion": "claim_support",
    "unit_id": "u_da6e158fb8116a621e0f2cf5",
    "reason": "شاهد: ادعای فنی یا پیش‌فرض پشتوانهٔ مستقیم ندارد."
  },
  {
    "criterion": "claim_support",
    "unit_id": "u_da6e158fb8116a621e0f2cf5",
    "reason": "شاهد: انتساب به کاربر شاهد مستقیم ندارد."
  },
  {
    "criterion": "claim_support",
    "unit_id": "u_3f32947603a126ae2c4a09d2",
    "reason": "شاهد: ادعای فنی یا پیش‌فرض پشتوانهٔ مستقیم ندارد."
  },
  {
    "criterion": "claim_support",
    "unit_id": "u_3f32947603a126ae2c4a09d2",
    "reason": "شاهد: انتساب به کاربر شاهد مستقیم ندارد."
  },
  {
    "criterion": "claim_support",
    "unit_id": "u_3f32947603a126ae2c4a09d2",
    "reason": "شاهد: انتساب آزاد کافی نیست؛ گزارش کاربر باید عبارت دقیق و محصور پیام باشد، یا ادعای فنی جدا بررسی شود."
  },
  {
    "criterion": "claim_support",
    "unit_id": "u_7a472c2c9af37fdd12ddf2cf",
    "reason": "شاهد: ادعای فنی یا پیش‌فرض پشتوانهٔ مستقیم ندارد."
  }
]
```

شواهد منتخب از `J.citations`:

```json
[
  {
    "evidence_id": "issue:11266:v2:b0b00ad71c9d0511",
    "quote": "1. Text is updated in string\n2. Button is pressed and rerun occurs (but the the text was never rendered. Widget is reset\n3. Widget reverts back to default",
    "version_limit": "محدودیت: نسخهٔ محصول منبع نامعلوم است؛ انطباق با محیط شما تأیید نشده است."
  }
]
```

## H2_B

Artifact: `artifacts\quality_v28_remaining\turns\holdout_r0_H2_B.json`

### پیش‌نویس 0

Draft: `0e464678cee59a755a495fdceb23a7ae58372292a76ab272aa3f6bf5102abf1a`

J = `$.requests[4].payload.messages[1].content (JSON)`

`J.draft.units[0].text` — `question` — `u_93111029b8c954b5ff812b81`

```text
آیا می‌توانید یک مشاهده جدید ارائه دهید که زمان دقیق طول عمر اعلان toast را نسبت به زمان شروع rerun صفحه جدا کند؟
```

`J.draft.units[1].text` — `next_step` — `u_cb0324dd764796fac01cd846`

```text
آیا می‌توانید یک مشاهده جدید ارائه دهید که زمان دقیق طول عمر اعلان st.toast را نسبت به زمان شروع rerun صفحه جدا کند؟
```

`J.draft.units[2].text` — `rationale` — `u_700ce4286b3ec82e00cda0fd`

```text
گزارش کاربر: A short `st.toast` notice disappears before it can be read when a page reruns after a button click. To diagnose this, باید مشاهده‌ای ارائه شود که زمان‌بندی نمایش و ناپدید شدن اعلان را نسبت به زمان شروع rerun صفحه جدا کند.
```

`J.draft.units[3].text` — `diagnostic.missing_fact` — `u_d7b07d96048340ac617bbc6d`

```text
یک مشاهده تجربی که زمان دقیق طول عمر اعلان toast را نسبت به زمان‌بندی rerun صفحه جدا کند.
```

`J.draft.units[4].text` — `claims.0.quote` — `u_3e63951266fb5a1b1c5ace3b`

```text
What you see is what I get after clicking "Update", not "rerun". When I click "rerun", I get the inconsistency.  It behaves the same whether or not the text input is in focus.
محدودیت: نسخهٔ محصول منبع نامعلوم است؛ انطباق با محیط شما تأیید نشده است.
```

رأی خام از `$.requests[4].raw_reply`: `accept`؛ رأی نگهبان: `repair`.

یافته‌های نگهبان برای همین draft:

```json
[
  {
    "criterion": "claim_support",
    "reason": "معنا: برچسب اختیاری نمی‌تواند عبارت فنیِ کشف‌شده از متن را به رویه تبدیل کند.",
    "unit_id": "u_cb0324dd764796fac01cd846"
  },
  {
    "criterion": "claim_support",
    "reason": "معنا: هر عبارت فنیِ کشف‌شده باید با شاهد منتخب مستقیم پشتیبانی شود.",
    "unit_id": "u_cb0324dd764796fac01cd846"
  },
  {
    "criterion": "claim_support",
    "reason": "معنا: برچسب اختیاری نمی‌تواند عبارت فنیِ کشف‌شده از متن را به رویه تبدیل کند.",
    "unit_id": "u_700ce4286b3ec82e00cda0fd"
  },
  {
    "criterion": "claim_support",
    "reason": "معنا: هر عبارت فنیِ کشف‌شده باید با شاهد منتخب مستقیم پشتیبانی شود.",
    "unit_id": "u_700ce4286b3ec82e00cda0fd"
  },
  {
    "criterion": "claim_support",
    "reason": "معنا: هر عبارت فنیِ کشف‌شده باید با شاهد منتخب مستقیم پشتیبانی شود.",
    "unit_id": "u_d7b07d96048340ac617bbc6d"
  },
  {
    "criterion": "claim_support",
    "reason": "شاهد: ادعای فنی یا پیش‌فرض پشتوانهٔ مستقیم ندارد.",
    "unit_id": "u_cb0324dd764796fac01cd846"
  },
  {
    "criterion": "claim_support",
    "reason": "شاهد: ادعای فنی یا پیش‌فرض پشتوانهٔ مستقیم ندارد.",
    "unit_id": "u_700ce4286b3ec82e00cda0fd"
  },
  {
    "criterion": "claim_support",
    "reason": "شاهد: انتساب به کاربر شاهد مستقیم ندارد.",
    "unit_id": "u_700ce4286b3ec82e00cda0fd"
  },
  {
    "criterion": "claim_support",
    "reason": "شاهد: ادعای فنی یا پیش‌فرض پشتوانهٔ مستقیم ندارد.",
    "unit_id": "u_d7b07d96048340ac617bbc6d"
  }
]
```

شواهد منتخب از `J.citations`:

```json
[
  {
    "evidence_id": "issue:11266:v3:child:02430ca0212480f1511f",
    "quote": "What you see is what I get after clicking \"Update\", not \"rerun\". When I click \"rerun\", I get the inconsistency.  It behaves the same whether or not the text input is in focus.",
    "version_limit": "محدودیت: نسخهٔ محصول منبع نامعلوم است؛ انطباق با محیط شما تأیید نشده است."
  }
]
```

### پیش‌نویس 1

Draft: `7845c9e44ca8ecc1671d4b95fa045c68d8dceb4f388b79cd068341e339535fc4`

J = `$.requests[6].payload.messages[1].content (JSON)`

`J.draft.units[0].text` — `question` — `u_e6ae19de5ccbbabb9cc9b259`

```text
آیا می‌توانید یک مشاهده جدید ارائه دهید که زمان دقیق طول عمر اعلان toast را نسبت به زمان شروع rerun صفحه جدا کند؟
```

`J.draft.units[1].text` — `next_step` — `u_505891a14552bb124ee38222`

```text
آیا می‌توانید یک مشاهده جدید ارائه دهید که زمان دقیق طول عمر اعلان st.toast را نسبت به زمان شروع rerun صفحه جدا کند؟
```

`J.draft.units[2].text` — `rationale` — `u_04064756015bb0e1c36ea777`

```text
برای تشخیص دقیق مشکل لازم است مشاهده‌ای ارائه شود که تفاوت بین زمان نمایش و زمان ناپدید شدن اعلان toast را نسبت به شروع عملیات rerun صفحه نشان دهد. این مشاهده به جدا کردن طول عمر اعلان از فرآیند rerun کمک می‌کند و در نتیجه تشخیص علت نمایش زودهنگام یا ناپدید شدن زودرس اعلان ممکن می‌شود.
```

`J.draft.units[3].text` — `diagnostic.missing_fact` — `u_1c848967f71cd970ff57156a`

```text
یک مشاهده تجربی که زمان دقیق طول عمر اعلان toast را نسبت به زمان‌بندی rerun صفحه جدا کند.
```

`J.draft.units[4].text` — `claims.0.quote` — `u_1a70cff297e7af8872531f33`

```text
What you see is what I get after clicking "Update", not "rerun". When I click "rerun", I get the inconsistency.  It behaves the same whether or not the text input is in focus.
محدودیت: نسخهٔ محصول منبع نامعلوم است؛ انطباق با محیط شما تأیید نشده است.
```

رأی خام از `$.requests[6].raw_reply`: `accept`؛ رأی نگهبان: `repair`.

یافته‌های نگهبان برای همین draft:

```json
[
  {
    "criterion": "claim_support",
    "unit_id": "u_505891a14552bb124ee38222",
    "reason": "معنا: برچسب اختیاری نمی‌تواند عبارت فنیِ کشف‌شده از متن را به رویه تبدیل کند."
  },
  {
    "criterion": "claim_support",
    "unit_id": "u_505891a14552bb124ee38222",
    "reason": "معنا: هر عبارت فنیِ کشف‌شده باید با شاهد منتخب مستقیم پشتیبانی شود."
  },
  {
    "criterion": "claim_support",
    "unit_id": "u_04064756015bb0e1c36ea777",
    "reason": "معنا: برچسب اختیاری نمی‌تواند عبارت فنیِ کشف‌شده از متن را به رویه تبدیل کند."
  },
  {
    "criterion": "claim_support",
    "unit_id": "u_04064756015bb0e1c36ea777",
    "reason": "معنا: هر عبارت فنیِ کشف‌شده باید با شاهد منتخب مستقیم پشتیبانی شود."
  },
  {
    "criterion": "claim_support",
    "unit_id": "u_1c848967f71cd970ff57156a",
    "reason": "معنا: برچسب اختیاری نمی‌تواند عبارت فنیِ کشف‌شده از متن را به رویه تبدیل کند."
  },
  {
    "criterion": "claim_support",
    "unit_id": "u_1c848967f71cd970ff57156a",
    "reason": "معنا: هر عبارت فنیِ کشف‌شده باید با شاهد منتخب مستقیم پشتیبانی شود."
  },
  {
    "criterion": "claim_support",
    "unit_id": "u_505891a14552bb124ee38222",
    "reason": "شاهد: ادعای فنی یا پیش‌فرض پشتوانهٔ مستقیم ندارد."
  },
  {
    "criterion": "claim_support",
    "unit_id": "u_04064756015bb0e1c36ea777",
    "reason": "شاهد: ادعای فنی یا پیش‌فرض پشتوانهٔ مستقیم ندارد."
  },
  {
    "criterion": "claim_support",
    "unit_id": "u_04064756015bb0e1c36ea777",
    "reason": "شاهد: انتساب به کاربر شاهد مستقیم ندارد."
  },
  {
    "criterion": "claim_support",
    "unit_id": "u_1c848967f71cd970ff57156a",
    "reason": "شاهد: ادعای فنی یا پیش‌فرض پشتوانهٔ مستقیم ندارد."
  }
]
```

شواهد منتخب از `J.citations`:

```json
[
  {
    "evidence_id": "issue:11266:v3:child:02430ca0212480f1511f",
    "quote": "What you see is what I get after clicking \"Update\", not \"rerun\". When I click \"rerun\", I get the inconsistency.  It behaves the same whether or not the text input is in focus.",
    "version_limit": "محدودیت: نسخهٔ محصول منبع نامعلوم است؛ انطباق با محیط شما تأیید نشده است."
  }
]
```
