import { useState } from 'react';
import { ArrowLeft, Copy, ExternalLink } from 'lucide-react';
import { Button, buttonVariants } from '@/components/ui/button';

const issuesUrl = 'https://github.com/TanMinhNgo/agent-series/issues';
const questions = [
  [
    'Làm sao bắt đầu một cuộc trò chuyện?',
    'Chọn Chat mới, chọn provider và model, rồi nhập yêu cầu. Bạn có thể chọn chế độ phù hợp trong ô nhập tin nhắn.',
  ],
  [
    'Làm sao dùng API key của tôi?',
    'Vào Cài đặt → Quản lý API key, chọn provider rồi xác minh và lưu key. Kiểm tra lại model sau khi kết nối.',
  ],
  [
    'Làm sao để AI trả lời dựa trên tài liệu?',
    'Vào Thư viện → Tài liệu RAG để tải PDF, DOCX hoặc Markdown. Chọn đúng Project và collection tài liệu trong chat; chờ tài liệu xử lý xong trước khi hỏi.',
  ],
  [
    'File AI tạo nằm ở đâu?',
    'File được gắn vào phản hồi và lưu trong Thư viện. Khi chat có file, nút File AI xuất hiện; nhấn nút để mở phần xem bên phải và tải file.',
  ],
  [
    'Tại sao không thấy model hoặc không gửi được tin nhắn?',
    'Kiểm tra API key, kết nối mạng và hạn mức của provider. Nếu dùng Ollama, mở Ollama và tải model, rồi dùng nút Kiểm tra lại Ollama trong menu chọn model.',
  ],
  [
    'Tôi có thể tùy chỉnh cách AI trả lời không?',
    'Trong Cài đặt, nhập Chỉ dẫn tùy chỉnh và lưu. Bạn cũng có thể bật hoặc tắt Tự học sở thích và xóa sở thích đã học.',
  ],
  [
    'Tại sao tôi không thể chỉnh sửa nội dung trong workspace?',
    'Vai trò viewer chỉ có quyền xem. Liên hệ owner của workspace để được cấp quyền editor nếu bạn cần tạo hoặc sửa nội dung.',
  ],
] as const;

export function SettingsHelpPage({
  navigate,
  support = false,
}: Readonly<{
  navigate: (to: string) => void;
  support?: boolean;
}>) {
  const [description, setDescription] = useState('');
  const [notice, setNotice] = useState('');
  const [copying, setCopying] = useState(false);
  const report = `Báo lỗi Agent Series\n\nMô tả vấn đề:\n${description.trim()}\n\nCác bước tái hiện:\n1. \n2. \n\nKết quả mong đợi:\n\nKết quả thực tế:\n\nThời điểm gặp lỗi:\n\nTrình duyệt / hệ điều hành:\n`;
  const copyReport = async () => {
    setNotice('');
    setCopying(true);
    try {
      await navigator.clipboard.writeText(report);
      setNotice('Đã sao chép mẫu báo lỗi. Điền các mục còn thiếu trước khi gửi.');
    } catch {
      setNotice('Không thể sao chép tự động. Hãy chọn và sao chép nội dung mẫu bên dưới.');
    } finally {
      setCopying(false);
    }
  };

  return (
    <main className="mx-auto w-full max-w-3xl space-y-6 px-4 py-8 sm:px-8 lg:px-12">
      <Button variant="ghost" onClick={() => navigate('/settings')}>
        <ArrowLeft /> Cài đặt
      </Button>
      <div>
        <p className="text-sm font-medium text-primary">Trợ giúp & hỗ trợ</p>
        <h1 className="mt-1 text-3xl font-semibold">{support ? 'Bạn cần hỗ trợ?' : 'Hướng dẫn sử dụng'}</h1>
        <p className="mt-2 text-sm text-muted-foreground">
          {support
            ? 'Mô tả vấn đề để nhóm phát triển có thể kiểm tra và tái hiện.'
            : 'Các thao tác thường dùng và cách xử lý khi gặp vấn đề.'}
        </p>
      </div>
      <nav aria-label="Trợ giúp và hỗ trợ" className="flex flex-wrap gap-2">
        <Button
          variant={support ? 'outline' : 'secondary'}
          aria-current={!support ? 'page' : undefined}
          onClick={() => navigate('/settings/help')}
        >
          Trợ giúp
        </Button>
        <Button
          variant={support ? 'secondary' : 'outline'}
          aria-current={support ? 'page' : undefined}
          onClick={() => navigate('/settings/support')}
        >
          Hỗ trợ
        </Button>
      </nav>
      {support ? (
        <section className="space-y-4 rounded-2xl border bg-card p-5">
          <h2 className="font-semibold">Báo lỗi hoặc góp ý</h2>
          <label className="grid gap-2 text-sm">
            <span>Vấn đề bạn gặp phải</span>
            <textarea
              className="min-h-28 rounded-lg border bg-background px-3 py-2"
              maxLength={4000}
              value={description}
              onChange={(event) => {
                setDescription(event.target.value);
                setNotice('');
              }}
              placeholder="Bạn đang làm gì, lỗi xuất hiện ở bước nào?"
            />
          </label>
          <p className="text-sm text-muted-foreground">
            Không đưa API key, mật khẩu hoặc nội dung riêng tư vào báo lỗi. Kiểm tra và che thông tin nhạy cảm
            trong ảnh trước khi đính kèm.
          </p>
          <label className="grid gap-2 text-sm">
            <span>Mẫu báo lỗi để sao chép</span>
            <textarea
              readOnly
              value={report}
              className="min-h-64 rounded-lg border bg-muted/40 px-3 py-2 font-mono text-xs"
            />
          </label>
          <div className="flex flex-wrap gap-2">
            <Button disabled={!description.trim() || copying} onClick={() => void copyReport()}>
              <Copy /> {copying ? 'Đang sao chép…' : 'Sao chép báo lỗi'}
            </Button>
            <a
              href={`${issuesUrl}/new`}
              target="_blank"
              rel="noopener noreferrer"
              className={buttonVariants({ variant: 'outline' })}
            >
              <ExternalLink /> Mở GitHub Issues
            </a>
          </div>
          {notice && (
            <p role="status" className="text-sm">
              {notice}
            </p>
          )}
          <p className="text-xs text-muted-foreground">
            GitHub yêu cầu đăng nhập. Bạn tự dán nội dung và gửi trên GitHub; mẫu này chưa được gửi đi. Nếu
            không truy cập được repository, gửi mẫu cho quản trị viên workspace.
          </p>
        </section>
      ) : (
        <>
          <section className="rounded-2xl border bg-card p-5">
            <h2 className="mb-3 font-semibold">Câu hỏi thường gặp</h2>
            <div className="divide-y">
              {questions.map(([question, answer]) => (
                <details key={question} className="group py-3">
                  <summary className="cursor-pointer rounded text-sm font-medium focus-visible:outline-2 focus-visible:outline-ring">
                    {question}
                  </summary>
                  <p className="mt-3 text-sm leading-relaxed text-muted-foreground">{answer}</p>
                </details>
              ))}
            </div>
          </section>
          <section className="space-y-3 rounded-2xl border bg-card p-5">
            <h2 className="font-semibold">Truy cập nhanh</h2>
            <div className="flex flex-wrap gap-2">
              <Button variant="outline" onClick={() => navigate('/settings/api-keys')}>
                Quản lý API key
              </Button>
              <Button variant="outline" onClick={() => navigate('/library')}>
                Thư viện
              </Button>
              <Button variant="outline" onClick={() => navigate('/settings/support')}>
                Báo lỗi / góp ý
              </Button>
            </div>
          </section>
        </>
      )}
    </main>
  );
}
