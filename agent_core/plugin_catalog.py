"""Curated, local metadata for the personal plugin catalog."""

from __future__ import annotations

from dataclasses import asdict, dataclass


@dataclass(frozen=True)
class CatalogPlugin:
    slug: str
    name: str
    description: str
    category: str
    capabilities: tuple[str, ...]
    setup_url: str
    featured: bool = False


def _plugin(
    slug: str, name: str, description: str, category: str, capabilities: tuple[str, ...] = ("search", "sync"), featured: bool = False
) -> CatalogPlugin:
    return CatalogPlugin(slug, name, description, category, capabilities, f"https://www.{slug.split('-')[0]}.com", featured)


CATALOG: tuple[CatalogPlugin, ...] = (
    # Năng suất
    _plugin("google-workspace", "Google Workspace", "Tìm dữ liệu trong Drive, Gmail và Calendar.", "productivity", ("search", "sync", "actions"), True),
    _plugin("notion", "Notion", "Tìm kiếm wiki, tài liệu và ghi chú workspace.", "productivity", featured=True),
    _plugin("asana", "Asana", "Theo dõi task, project và tiến độ công việc.", "productivity"),
    _plugin("clickup", "ClickUp", "Tra cứu task, docs và kế hoạch trong ClickUp.", "productivity"),
    _plugin("todoist", "Todoist", "Quản lý việc cần làm và ưu tiên hằng ngày.", "productivity", ("search", "actions")),
    # Sáng tạo
    _plugin("figma", "Figma", "Tìm file thiết kế, prototype và nhận xét.", "creative", featured=True),
    _plugin("miro", "Miro", "Tra cứu whiteboard, workshop và sơ đồ ý tưởng.", "creative"),
    _plugin("framer", "Framer", "Tìm dự án website và nội dung đã xuất bản.", "creative"),
    _plugin("behance", "Behance", "Khám phá portfolio và cảm hứng thiết kế.", "creative", ("search",)),
    _plugin("dribbble", "Dribbble", "Tìm tham khảo giao diện và sản phẩm sáng tạo.", "creative", ("search",)),
    # Công cụ cho nhà phát triển
    _plugin("github", "GitHub", "Đọc repository, pull request, issue và tài liệu.", "developer", featured=True),
    _plugin("gitlab", "GitLab", "Tra cứu source code, issue và pipeline CI/CD.", "developer"),
    _plugin("linear", "Linear", "Tổng hợp issue, sprint và kế hoạch sản phẩm.", "developer"),
    _plugin("vercel", "Vercel", "Theo dõi deployment, project và log build.", "developer"),
    _plugin("sentry", "Sentry", "Tìm lỗi ứng dụng và theo dõi hiệu năng.", "developer"),
    # Doanh nghiệp & vận hành
    _plugin("hubspot", "HubSpot", "Tra cứu khách hàng, pipeline và hoạt động bán hàng.", "business"),
    _plugin("intercom", "Intercom", "Tìm hội thoại hỗ trợ và thông tin khách hàng.", "business"),
    _plugin("shopify", "Shopify", "Theo dõi sản phẩm, đơn hàng và cửa hàng.", "business", ("search", "sync", "actions")),
    _plugin("jira", "Jira", "Quản lý ticket, sprint và quy trình vận hành.", "business"),
    _plugin("zendesk", "Zendesk", "Tra cứu ticket và kiến thức hỗ trợ khách hàng.", "business"),
    # Giáo dục & nghiên cứu
    _plugin("coursera", "Coursera", "Tìm khóa học và nội dung học tập.", "education", ("search",)),
    _plugin("khanacademy", "Khan Academy", "Khám phá tài liệu học tập theo chủ đề.", "education", ("search",)),
    _plugin("udemy", "Udemy", "Tìm khóa học kỹ năng và tài nguyên đào tạo.", "education", ("search",)),
    _plugin("zotero", "Zotero", "Tra cứu thư mục tài liệu và trích dẫn nghiên cứu.", "education"),
    _plugin("wolfram", "Wolfram", "Tìm kiến thức, tính toán và dữ liệu tham khảo.", "education", ("search",)),
    # Dữ liệu & phân tích
    _plugin("posthog", "PostHog", "Khám phá event, insight và session replay.", "analytics"),
    _plugin("googleanalytics", "Google Analytics", "Theo dõi traffic và hành vi người dùng.", "analytics"),
    _plugin("mixpanel", "Mixpanel", "Phân tích funnel, retention và hành vi sản phẩm.", "analytics"),
    _plugin("looker", "Looker", "Tìm dashboard và báo cáo dữ liệu doanh nghiệp.", "analytics"),
    _plugin("datadog", "Datadog", "Theo dõi metric, log và độ ổn định hệ thống.", "analytics"),
    # Liên lạc
    _plugin("slack", "Slack", "Tìm kiếm channel, thread và thảo luận nhóm.", "communication", ("search", "actions"), True),
    _plugin("microsoft-teams", "Microsoft Teams", "Tra cứu chat, cuộc họp và nội dung Teams.", "communication"),
    _plugin("discord", "Discord", "Tìm thảo luận và thông báo trong cộng đồng.", "communication", ("search",)),
    _plugin("zoom", "Zoom", "Tìm thông tin cuộc họp và bản ghi Zoom.", "communication"),
    _plugin("gmail", "Gmail", "Tìm email và quản lý hộp thư công việc.", "communication", ("search", "actions")),
    # Bảo mật
    _plugin("1password", "1Password", "Tra cứu vault và trạng thái bảo mật đã cấp quyền.", "security"),
    _plugin("okta", "Okta", "Theo dõi ứng dụng, danh tính và quyền truy cập.", "security"),
    _plugin("cloudflare", "Cloudflare", "Theo dõi DNS, bảo mật và hiệu năng edge.", "security"),
    _plugin("snyk", "Snyk", "Kiểm tra lỗ hổng dependency và source code.", "security"),
    _plugin("virustotal", "VirusTotal", "Tra cứu reputation của file, domain và URL.", "security", ("search",)),
    # Tài chính
    _plugin("stripe", "Stripe", "Theo dõi thanh toán, khách hàng và hóa đơn.", "finance"),
    _plugin("quickbooks", "QuickBooks", "Tra cứu sổ sách, hóa đơn và chi phí.", "finance"),
    _plugin("xero", "Xero", "Theo dõi kế toán và dòng tiền doanh nghiệp.", "finance"),
    _plugin("wise", "Wise", "Quản lý giao dịch và chuyển tiền quốc tế.", "finance"),
    _plugin("coinbase", "Coinbase", "Theo dõi tài sản số và giao dịch.", "finance"),
    # Chăm sóc sức khỏe
    _plugin("fitbit", "Fitbit", "Xem hoạt động, giấc ngủ và chỉ số sức khỏe.", "health"),
    _plugin("garmin", "Garmin", "Theo dõi luyện tập và dữ liệu vận động.", "health"),
    _plugin("strava", "Strava", "Xem hoạt động thể thao và mục tiêu luyện tập.", "health"),
    _plugin("headspace", "Headspace", "Theo dõi thói quen thiền và chăm sóc tinh thần.", "health"),
    _plugin("peloton", "Peloton", "Theo dõi lớp tập và tiến độ vận động.", "health"),
    # Du lịch
    _plugin("googlemaps", "Google Maps", "Tìm địa điểm, tuyến đường và thông tin di chuyển.", "travel", ("search",)),
    _plugin("bookingdotcom", "Booking.com", "Tìm chỗ ở và thông tin đặt phòng.", "travel", ("search",)),
    _plugin("airbnb", "Airbnb", "Khám phá chỗ ở và kế hoạch lưu trú.", "travel", ("search",)),
    _plugin("expedia", "Expedia", "Tìm chuyến bay, khách sạn và hành trình.", "travel", ("search",)),
    _plugin("tripadvisor", "Tripadvisor", "Tìm đánh giá địa điểm và gợi ý du lịch.", "travel", ("search",)),
    # Giải trí
    _plugin("spotify", "Spotify", "Tìm playlist, nghệ sĩ và podcast.", "entertainment", ("search",)),
    _plugin("youtube", "YouTube", "Tìm video, kênh và nội dung giải trí.", "entertainment", ("search",)),
    _plugin("netflix", "Netflix", "Khám phá nội dung phim và chương trình.", "entertainment", ("search",)),
    _plugin("twitch", "Twitch", "Tìm livestream và kênh sáng tạo.", "entertainment", ("search",)),
    _plugin("steam", "Steam", "Theo dõi game, thư viện và cộng đồng.", "entertainment", ("search",)),
    # Khác
    _plugin("dropbox", "Dropbox", "Tìm kiếm và đồng bộ file từ Dropbox.", "other"),
    _plugin("onedrive-sharepoint", "OneDrive & SharePoint", "Tìm tài liệu trong hệ sinh thái Microsoft.", "other"),
    _plugin("trello", "Trello", "Tra cứu bảng, thẻ và kế hoạch công việc.", "other"),
    _plugin("airtable", "Airtable", "Tìm bản ghi và dữ liệu trong base.", "other"),
    _plugin("zapier", "Zapier", "Theo dõi automation và kết nối ứng dụng.", "other", ("search", "sync", "actions")),
)


def catalog_json(item: CatalogPlugin, installed_plugin_id: str | None = None) -> dict:
    result = asdict(item)
    result["capabilities"] = list(item.capabilities)
    result["installedPluginId"] = installed_plugin_id
    return result


def find_catalog_plugin(slug: str) -> CatalogPlugin | None:
    return next((item for item in CATALOG if item.slug == slug), None)
