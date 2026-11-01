import Foundation
import UIKit

/// Full-screen image viewer: a paging scroll view with one zooming scroll view per image. Pinch or double-tap to
/// zoom, swipe sideways to page, swipe down (or tap the close button) to leave. The `open` reply comes when the
/// viewer closes, with the index it closed on; page changes go to Python as `ImageViewer.index` events.
final class ImageViewerModule: NSObject, PxModule {
    static let moduleName = "ImageViewer"
    private static weak var current: PxImageViewerController?

    required override init() { super.init() }

    func call(_ ctx: PxModuleContext, _ method: String, _ args: [Any], _ reply: @escaping PxReply) {
        DispatchQueue.main.async {
            switch method {
            case "open": self.open(ctx, args, reply)
            case "close":
                Self.current?.close()
                reply(nil, nil)
            default: reply(nil, "unknown native call ImageViewer.\(method)")
            }
        }
    }

    private func open(_ ctx: PxModuleContext, _ args: [Any], _ reply: @escaping PxReply) {
        if Self.current != nil { reply(nil, "an image viewer is already open"); return }
        let uris = (args.first as? [Any] ?? []).compactMap { $0 as? String }
        if uris.isEmpty { reply(nil, "no images to show"); return }
        guard let top = ctx.presenter() else { reply(nil, "no view controller to present the image viewer"); return }
        let o = (args.count > 1 ? args[1] as? [String: Any] : nil) ?? [:]
        let token = ctx.retain(self)
        let vc = PxImageViewerController(uris: uris, options: o)
        vc.onIndex = { i in ctx.emit("ImageViewer.index", ["index": i]) }
        vc.onClose = { i in
            ctx.release(token)
            reply(["index": i], nil)
        }
        Self.current = vc
        top.present(vc, animated: true)
    }
}

final class PxImageViewerController: UIViewController, UIScrollViewDelegate, UIGestureRecognizerDelegate {
    var onIndex: ((Int) -> Void)?
    var onClose: ((Int) -> Void)?

    private let uris: [String]
    private var index: Int
    private let background: UIColor
    private let swipeToClose: Bool
    private let doubleTapZoom: Bool
    private let maxZoom: CGFloat
    private let showCount: Bool
    private let closeLabel: String
    private let pager = UIScrollView()
    private var pages: [PxZoomPage] = []
    private let closeButton = UIButton(type: .system)
    private let counter = UILabel()
    private var chromeHidden = false
    private var laidOutWidth: CGFloat = 0
    private var closed = false
    private lazy var dismissPan = UIPanGestureRecognizer(target: self, action: #selector(dragged(_:)))

    init(uris: [String], options o: [String: Any]) {
        self.uris = uris
        index = min(max((o["index"] as? NSNumber)?.intValue ?? 0, 0), uris.count - 1)
        background = PxImageViewerController.color(o["background"] as? String) ?? .black
        swipeToClose = (o["swipeToClose"] as? Bool) ?? true
        doubleTapZoom = (o["doubleTapZoom"] as? Bool) ?? true
        maxZoom = CGFloat(max((o["maxZoom"] as? NSNumber)?.doubleValue ?? 4, 1))
        showCount = (o["showCount"] as? Bool) ?? true
        closeLabel = (o["closeLabel"] as? String) ?? "Close"
        super.init(nibName: nil, bundle: nil)
        modalPresentationStyle = .overFullScreen
        modalTransitionStyle = .crossDissolve
        modalPresentationCapturesStatusBarAppearance = true
    }

    required init?(coder: NSCoder) { fatalError("init(coder:) is not used") }

    override var preferredStatusBarStyle: UIStatusBarStyle { .lightContent }
    override var prefersStatusBarHidden: Bool { chromeHidden }
    override var preferredStatusBarUpdateAnimation: UIStatusBarAnimation { .fade }

    override func viewDidLoad() {
        super.viewDidLoad()
        view.backgroundColor = background
        pager.isPagingEnabled = true
        pager.showsHorizontalScrollIndicator = false
        pager.showsVerticalScrollIndicator = false
        pager.contentInsetAdjustmentBehavior = .never
        pager.delegate = self
        view.addSubview(pager)
        for (i, uri) in uris.enumerated() {
            let page = PxZoomPage(uri: uri, maxZoom: maxZoom, doubleTap: doubleTapZoom)
            page.accessibilityLabel = uris.count > 1 ? "Image \(i + 1) of \(uris.count)" : "Image"
            page.onTap = { [weak self] in self?.toggleChrome() }
            pager.addSubview(page)
            pages.append(page)
        }

        closeButton.setImage(UIImage(systemName: "xmark", withConfiguration: UIImage.SymbolConfiguration(pointSize: 17, weight: .semibold)), for: .normal)
        closeButton.tintColor = .white
        closeButton.backgroundColor = UIColor(white: 1, alpha: 0.16)
        closeButton.layer.cornerRadius = 22
        closeButton.accessibilityLabel = closeLabel
        closeButton.addTarget(self, action: #selector(closeTapped), for: .touchUpInside)
        view.addSubview(closeButton)
        counter.textColor = .white
        counter.font = .systemFont(ofSize: 16, weight: .semibold)
        counter.textAlignment = .center
        counter.isHidden = !showCount || uris.count < 2
        view.addSubview(counter)
        updateCounter()

        dismissPan.delegate = self
        dismissPan.isEnabled = swipeToClose
        view.addGestureRecognizer(dismissPan)
        pager.panGestureRecognizer.require(toFail: dismissPan)
        for page in pages { page.panGestureRecognizer.require(toFail: dismissPan) }
        loadAround(index)
    }

    override func viewDidLayoutSubviews() {
        super.viewDidLayoutSubviews()
        let b = view.bounds
        if laidOutWidth != b.width {
            laidOutWidth = 0  // no page changes while the pager is resized
            pager.frame = b
            pager.contentSize = CGSize(width: b.width * CGFloat(pages.count), height: b.height)
            for (i, page) in pages.enumerated() {
                page.frame = CGRect(x: b.width * CGFloat(i), y: 0, width: b.width, height: b.height)
            }
            pager.contentOffset = CGPoint(x: b.width * CGFloat(index), y: 0)
            laidOutWidth = b.width
        }
        let inset = view.safeAreaInsets
        closeButton.frame = CGRect(x: max(inset.left, 0) + 16, y: inset.top + 8, width: 44, height: 44)
        counter.frame = CGRect(x: 80, y: inset.top + 8, width: max(b.width - 160, 0), height: 44)
    }

    override func viewWillTransition(to size: CGSize, with coordinator: UIViewControllerTransitionCoordinator) {
        super.viewWillTransition(to: size, with: coordinator)
        pages[index].resetZoom(animated: false)
    }

    func close() {
        if closed { return }
        presentingViewController?.dismiss(animated: true) { [weak self] in self?.finish() }
    }

    @objc private func closeTapped() { close() }

    private func finish() {
        if closed { return }
        closed = true
        onClose?(index)
        onClose = nil
    }

    override func viewDidDisappear(_ animated: Bool) {
        super.viewDidDisappear(animated)
        if presentingViewController == nil { finish() }
    }

    // MARK: paging

    func scrollViewDidScroll(_ scrollView: UIScrollView) {
        guard scrollView === pager, pager.bounds.width > 0, laidOutWidth > 0 else { return }
        let i = min(max(Int((pager.contentOffset.x / pager.bounds.width).rounded()), 0), pages.count - 1)
        if i == index { return }
        index = i
        updateCounter()
        loadAround(i)
        onIndex?(i)
    }

    func scrollViewDidEndDecelerating(_ scrollView: UIScrollView) {
        guard scrollView === pager else { return }
        for (i, page) in pages.enumerated() where i != index { page.resetZoom(animated: false) }
    }

    private func loadAround(_ i: Int) {
        for j in max(i - 1, 0)...min(i + 1, pages.count - 1) { pages[j].load() }
    }

    private func updateCounter() {
        counter.text = "\(index + 1) / \(uris.count)"
    }

    private func toggleChrome() {
        chromeHidden.toggle()
        UIView.animate(withDuration: 0.2) {
            self.closeButton.alpha = self.chromeHidden ? 0 : 1
            self.counter.alpha = self.chromeHidden ? 0 : 1
            self.setNeedsStatusBarAppearanceUpdate()
        }
    }

    // MARK: swipe to close

    func gestureRecognizerShouldBegin(_ g: UIGestureRecognizer) -> Bool {
        guard g === dismissPan else { return true }
        if pages[index].zoomScale > pages[index].minimumZoomScale + 0.01 || pager.isDecelerating { return false }
        let v = dismissPan.velocity(in: view)
        return abs(v.y) > abs(v.x)
    }

    @objc private func dragged(_ g: UIPanGestureRecognizer) {
        let page = pages[index]
        let dy = g.translation(in: view).y
        let h = max(view.bounds.height, 1)
        switch g.state {
        case .changed:
            page.transform = CGAffineTransform(translationX: 0, y: dy)
            let fade = 1 - min(abs(dy) / (h * 0.6), 1) * 0.85
            view.backgroundColor = background.withAlphaComponent(fade)
            closeButton.alpha = chromeHidden ? 0 : fade
            counter.alpha = closeButton.alpha
        case .ended, .cancelled, .failed:
            let vy = g.velocity(in: view).y
            if g.state == .ended && (abs(dy) > 120 || abs(vy) > 800) {
                let out = (dy == 0 ? vy : dy) < 0 ? -h : h
                UIView.animate(withDuration: 0.22, delay: 0, options: [.curveEaseOut], animations: {
                    page.transform = CGAffineTransform(translationX: 0, y: out)
                    self.view.backgroundColor = self.background.withAlphaComponent(0)
                    self.closeButton.alpha = 0
                    self.counter.alpha = 0
                }, completion: { _ in
                    self.presentingViewController?.dismiss(animated: false) { [weak self] in self?.finish() }
                })
            } else {
                UIView.animate(withDuration: 0.35, delay: 0, usingSpringWithDamping: 0.85, initialSpringVelocity: 0,
                               options: [.allowUserInteraction], animations: {
                    page.transform = .identity
                    self.view.backgroundColor = self.background
                    self.closeButton.alpha = self.chromeHidden ? 0 : 1
                    self.counter.alpha = self.closeButton.alpha
                })
            }
        default: break
        }
    }

    static func color(_ s: String?) -> UIColor? {
        guard var hex = s?.trimmingCharacters(in: .whitespaces), hex.hasPrefix("#") else { return nil }
        hex.removeFirst()
        if hex.count == 3 { hex = hex.map { "\($0)\($0)" }.joined() }
        guard hex.count == 6 || hex.count == 8, let v = UInt64(hex, radix: 16) else { return nil }
        let a = hex.count == 8 ? CGFloat(v & 0xff) / 255 : 1
        let rgb = hex.count == 8 ? v >> 8 : v
        return UIColor(red: CGFloat((rgb >> 16) & 0xff) / 255, green: CGFloat((rgb >> 8) & 0xff) / 255,
                       blue: CGFloat(rgb & 0xff) / 255, alpha: a)
    }
}

/// One page: the image laid out aspect-fit, zoomed by the scroll view and kept centered while smaller than the page.
final class PxZoomPage: UIScrollView, UIScrollViewDelegate {
    var onTap: (() -> Void)?

    private let uri: String
    private let imageView = UIImageView()
    private let spinner = UIActivityIndicatorView(style: .large)
    private let failed = UILabel()
    private var started = false
    private var lastSize = CGSize.zero

    init(uri: String, maxZoom: CGFloat, doubleTap: Bool) {
        self.uri = uri
        super.init(frame: .zero)
        delegate = self
        minimumZoomScale = 1
        maximumZoomScale = maxZoom
        showsHorizontalScrollIndicator = false
        showsVerticalScrollIndicator = false
        contentInsetAdjustmentBehavior = .never
        decelerationRate = .fast
        isAccessibilityElement = true
        accessibilityTraits = .image
        imageView.contentMode = .scaleAspectFit
        addSubview(imageView)
        spinner.color = .white
        addSubview(spinner)
        failed.text = "Couldn't load this image"
        failed.textColor = UIColor(white: 1, alpha: 0.7)
        failed.font = .systemFont(ofSize: 15)
        failed.textAlignment = .center
        failed.isHidden = true
        addSubview(failed)

        let single = UITapGestureRecognizer(target: self, action: #selector(tapped))
        addGestureRecognizer(single)
        if doubleTap {
            let double = UITapGestureRecognizer(target: self, action: #selector(doubleTapped(_:)))
            double.numberOfTapsRequired = 2
            addGestureRecognizer(double)
            single.require(toFail: double)
        }
    }

    required init?(coder: NSCoder) { fatalError("init(coder:) is not used") }

    override func layoutSubviews() {
        super.layoutSubviews()
        spinner.center = CGPoint(x: bounds.midX, y: bounds.midY)
        failed.frame = CGRect(x: bounds.minX + 24, y: bounds.midY - 20, width: max(bounds.width - 48, 0), height: 40)
        if bounds.size != lastSize {
            lastSize = bounds.size
            fit()
        }
    }

    func load() {
        if started { return }
        started = true
        spinner.startAnimating()
        PxImageLoader.load(uri) { [weak self] image in
            guard let self = self else { return }
            self.spinner.stopAnimating()
            if let image = image {
                self.imageView.image = image
                self.fit()
            } else {
                self.failed.isHidden = false
                self.started = false
            }
        }
    }

    func resetZoom(animated: Bool) {
        if zoomScale != minimumZoomScale { setZoomScale(minimumZoomScale, animated: animated) }
    }

    private func fit() {
        zoomScale = 1
        guard let image = imageView.image, image.size.width > 0, image.size.height > 0, bounds.width > 0 else {
            imageView.frame = bounds
            return
        }
        let s = min(bounds.width / image.size.width, bounds.height / image.size.height)
        let size = CGSize(width: (image.size.width * s).rounded(), height: (image.size.height * s).rounded())
        imageView.frame = CGRect(origin: .zero, size: size)
        contentSize = size
        center()
    }

    private func center() {
        let x = max((bounds.width - contentSize.width) / 2, 0)
        let y = max((bounds.height - contentSize.height) / 2, 0)
        contentInset = UIEdgeInsets(top: y, left: x, bottom: y, right: x)
    }

    func viewForZooming(in scrollView: UIScrollView) -> UIView? { imageView }

    func scrollViewDidZoom(_ scrollView: UIScrollView) { center() }

    @objc private func tapped() { onTap?() }

    @objc private func doubleTapped(_ g: UITapGestureRecognizer) {
        if imageView.image == nil { return }
        if zoomScale > minimumZoomScale + 0.01 {
            setZoomScale(minimumZoomScale, animated: true)
            return
        }
        let scale = min(maximumZoomScale, 2.5)
        let p = g.location(in: imageView)
        let w = bounds.width / scale, h = bounds.height / scale
        zoom(to: CGRect(x: p.x - w / 2, y: p.y - h / 2, width: w, height: h), animated: true)
    }
}

/// Loads `http(s)://` and `data:` URLs with URLSession (its shared URL cache keeps repeat opens fast), and
/// `file://` URLs or plain paths from disk. Decodes off the main thread; calls back on main.
enum PxImageLoader {
    static func load(_ uri: String, _ done: @escaping (UIImage?) -> Void) {
        func decode(_ data: Data?) {
            let image = data.flatMap { UIImage(data: $0) }
            let ready = image.map { $0.preparingForDisplay() ?? $0 }
            DispatchQueue.main.async { done(ready) }
        }
        if uri.hasPrefix("http://") || uri.hasPrefix("https://") || uri.hasPrefix("data:"), let url = URL(string: uri) {
            URLSession.shared.dataTask(with: url) { data, response, _ in
                let ok = (response as? HTTPURLResponse).map { (200..<300).contains($0.statusCode) } ?? true
                decode(ok ? data : nil)
            }.resume()
            return
        }
        let path = uri.hasPrefix("file://") ? (URL(string: uri)?.path ?? uri) : uri
        DispatchQueue.global(qos: .userInitiated).async { decode(FileManager.default.contents(atPath: path)) }
    }
}
