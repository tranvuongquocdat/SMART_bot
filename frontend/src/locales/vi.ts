// Từ điển tiếng Việt — khóa phẳng "namespace.key". vi là ngôn ngữ gốc/fallback.
export const vi: Record<string, string> = {
  // chung
  'common.save': 'Lưu',
  'common.saving': 'Đang lưu…',
  'common.loading': 'Đang tải…',
  'common.saved': 'Đã lưu',
  'common.saveError': 'Lưu thất bại.',
  'common.language': 'Ngôn ngữ',

  // trang Cài đặt
  'settings.title': 'Cài đặt',
  'settings.subtitle': 'Thông tin tài khoản, AI và tổ chức.',
  'settings.tab.account': 'Tài khoản',
  'settings.tab.general': 'Chung',

  // tab Tài khoản
  'settings.account.email': 'Email',
  'settings.account.role': 'Vai trò',
  'settings.account.google': 'Google',
  'settings.account.googleLinked': 'Đã liên kết',
  'settings.account.googleUnlinked': 'Chưa liên kết',
  'settings.account.plan': 'Gói dịch vụ',
  'settings.account.planExpiry': '(hết hạn {date})',
  'settings.account.costCap': 'Cost cap/ngày',
  'settings.account.displayName': 'Tên hiển thị',
  'settings.account.displayNamePlaceholder': 'Nhập tên hiển thị',
  'settings.account.savedName': 'Đã lưu tên hiển thị.',

  // tab Chung
  'settings.general.displayName': 'Tên hiển thị',
  'settings.general.displayNamePlaceholder': 'Tên hiển thị',
  'settings.general.tz': 'Múi giờ',
  'settings.general.language': 'Ngôn ngữ',
  'settings.general.saved': 'Đã lưu cài đặt chung.',

  // bộ chọn ngôn ngữ
  'lang.vi': 'Tiếng Việt',
  'lang.en': 'English',
};
