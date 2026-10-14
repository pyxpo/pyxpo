import UIKit

/// Container whose children are placed by OpApplier from engine frames. No auto layout, no layoutSubviews.
class PxGroup: UIView {}

/// Root view, pinned to the safe area. Reports size and trait changes.
final class PxRoot: UIView {
    var onSize: ((CGSize) -> Void)?
    var onTraits: (() -> Void)?

    override func layoutSubviews() {
        super.layoutSubviews()
        onSize?(bounds.size)
    }

    override func traitCollectionDidChange(_ previous: UITraitCollection?) {
        super.traitCollectionDidChange(previous)
        onTraits?()
    }
}

/// ScrollView host: `content` is placed by the engine's synthetic content node.
final class ScrollHost: UIScrollView {
    let content = PxGroup()

    override init(frame: CGRect) {
        super.init(frame: frame)
        contentInsetAdjustmentBehavior = .never
        addSubview(content)
    }

    required init?(coder: NSCoder) { fatalError("init(coder:) not supported") }
}

/// Label that draws inside padding + border insets (the engine's frame includes them).
final class PxLabel: UILabel {
    var insets = UIEdgeInsets.zero

    override func drawText(in rect: CGRect) {
        super.drawText(in: rect.inset(by: insets))
    }
}

final class PxTextField: UITextField {
    var insets = UIEdgeInsets.zero

    override func textRect(forBounds bounds: CGRect) -> CGRect { bounds.inset(by: insets) }
    override func editingRect(forBounds bounds: CGRect) -> CGRect { bounds.inset(by: insets) }
    override func placeholderRect(forBounds bounds: CGRect) -> CGRect { bounds.inset(by: insets) }
}
