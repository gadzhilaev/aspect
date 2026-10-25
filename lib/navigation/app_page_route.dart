import 'package:flutter/cupertino.dart';

/// Push со слайдом и свайпом «назад» не только с края, а с любой точки экрана.
class AppPageRoute<T> extends CupertinoPageRoute<T> {
  AppPageRoute({
    required WidgetBuilder builder,
    super.title,
    super.settings,
    super.maintainState = true,
    super.fullscreenDialog = false,
  }) : super(
          builder: (context) => _FullWidthSwipeBack(
            child: builder(context),
          ),
        );

  @override
  Duration get transitionDuration => const Duration(milliseconds: 380);

  @override
  Duration get reverseTransitionDuration => const Duration(milliseconds: 320);
}

class _FullWidthSwipeBack extends StatefulWidget {
  const _FullWidthSwipeBack({required this.child});

  final Widget child;

  @override
  State<_FullWidthSwipeBack> createState() => _FullWidthSwipeBackState();
}

class _FullWidthSwipeBackState extends State<_FullWidthSwipeBack> {
  double _dx = 0;
  bool _tracking = false;

  void _onStart(DragStartDetails _) {
    // Не мешаем вводу текста / диалогам.
    if (FocusManager.instance.primaryFocus?.hasFocus == true) return;
    _dx = 0;
    _tracking = true;
  }

  void _onUpdate(DragUpdateDetails d) {
    if (!_tracking) return;
    _dx += d.delta.dx;
  }

  void _onEnd(DragEndDetails d) {
    if (!_tracking) return;
    _tracking = false;
    final vx = d.velocity.pixelsPerSecond.dx;
    final shouldPop = _dx > 72 || (_dx > 36 && vx > 600);
    _dx = 0;
    if (shouldPop && mounted) {
      Navigator.of(context).maybePop();
    }
  }

  void _onCancel() {
    _tracking = false;
    _dx = 0;
  }

  @override
  Widget build(BuildContext context) {
    // Свайп вправо с любой точки → назад (не только с края).
    return GestureDetector(
      behavior: HitTestBehavior.translucent,
      onHorizontalDragStart: _onStart,
      onHorizontalDragUpdate: _onUpdate,
      onHorizontalDragEnd: _onEnd,
      onHorizontalDragCancel: _onCancel,
      child: widget.child,
    );
  }
}
