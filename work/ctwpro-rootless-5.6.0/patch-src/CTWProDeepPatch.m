#import <Foundation/Foundation.h>
#import <UIKit/UIKit.h>
#import <dlfcn.h>
#import <objc/runtime.h>
#import <pthread.h>
#import <stdatomic.h>
#import <stdint.h>
#import <string.h>
#import <unistd.h>

static _Atomic(uintptr_t) gOriginalViewDidLoad;
static _Atomic(uintptr_t) gOriginalUpdateUITimer;
static _Atomic(uintptr_t) gOriginalAlertHandler;
static _Atomic(uintptr_t) gOriginalSetNeedCheckIP;
static _Atomic(uintptr_t) gOriginalSetNeedFlushIP;
static _Atomic(uintptr_t) gOriginalLabelSetText;

static IMP LoadOriginal(_Atomic(uintptr_t) *storage) {
    return (IMP)atomic_load_explicit(storage, memory_order_acquire);
}

static void StoreOriginalOnce(_Atomic(uintptr_t) *storage, IMP implementation) {
    uintptr_t expected = 0;
    atomic_compare_exchange_strong_explicit(
        storage,
        &expected,
        (uintptr_t)implementation,
        memory_order_release,
        memory_order_relaxed
    );
}

static id ObjectProperty(id object, SEL selector) {
    if (object == nil || ![object respondsToSelector:selector]) {
        return nil;
    }
    IMP implementation = [object methodForSelector:selector];
    return ((id (*)(id, SEL))implementation)(object, selector);
}

static BOOL IsDonationAction(NSString *action) {
    static NSSet<NSString *> *actions;
    static dispatch_once_t onceToken;
    dispatch_once(&onceToken, ^{
        actions = [NSSet setWithArray:@[
            @"recharge:",
            @"scanQRCode:",
            @"showQRCodeView:"
        ]];
    });
    return [actions containsObject:action];
}

static BOOL ControlHasDonationAction(UIControl *control) {
    for (id target in control.allTargets) {
        NSArray<NSString *> *actions = [control actionsForTarget:target
                                                 forControlEvent:UIControlEventAllEvents];
        for (NSString *action in actions) {
            if (IsDonationAction(action)) {
                return YES;
            }
        }
    }
    return NO;
}

static void RepairViewTree(UIView *view) {
    if ([view isKindOfClass:[UIControl class]]) {
        UIControl *control = (UIControl *)view;
        if (ControlHasDonationAction(control)) {
            control.enabled = NO;
            control.hidden = YES;
        } else {
            control.enabled = YES;
            control.userInteractionEnabled = YES;
        }
    }
    for (UIView *subview in view.subviews) {
        RepairViewTree(subview);
    }
}

static void RepairController(id controller) {
    if (controller == nil) {
        return;
    }

    IMP setNeedCheck = LoadOriginal(&gOriginalSetNeedCheckIP);
    if (setNeedCheck != NULL) {
        ((void (*)(id, SEL, BOOL))setNeedCheck)(controller, @selector(setIsNeedCheckIP:), NO);
    }
    IMP setNeedFlush = LoadOriginal(&gOriginalSetNeedFlushIP);
    if (setNeedFlush != NULL) {
        ((void (*)(id, SEL, BOOL))setNeedFlush)(controller, @selector(setIsNeedFlushIP:), NO);
    }

    UILabel *expireDate = ObjectProperty(controller, @selector(expireDate));
    if ([expireDate isKindOfClass:[UILabel class]]) {
        expireDate.text = @"测试权限:永久";
    }
    UILabel *statusDescription = ObjectProperty(controller, @selector(statusDescription));
    if ([statusDescription isKindOfClass:[UILabel class]]) {
        statusDescription.text = @"网络节点已就绪";
    }
    UIButton *manageredApd = ObjectProperty(controller, @selector(manageredApd));
    if ([manageredApd isKindOfClass:[UIButton class]]) {
        manageredApd.enabled = YES;
        manageredApd.userInteractionEnabled = YES;
    }
    UIView *rootView = ObjectProperty(controller, @selector(view));
    if ([rootView isKindOfClass:[UIView class]]) {
        RepairViewTree(rootView);
    }

    NSUserDefaults *defaults = [NSUserDefaults standardUserDefaults];
    [defaults setBool:YES forKey:@"CTWProDeepPatchLocalAuthorization"];
}

static void NoopAction(id self, SEL _cmd, id sender) {
    (void)self;
    (void)_cmd;
    (void)sender;
}

static void NoopVoid(id self, SEL _cmd) {
    (void)self;
    (void)_cmd;
}

static BOOL AlwaysNo(id self, SEL _cmd) {
    (void)self;
    (void)_cmd;
    return NO;
}

static void ForceNoCheck(id self, SEL _cmd, BOOL value) {
    (void)value;
    IMP original = LoadOriginal(&gOriginalSetNeedCheckIP);
    if (original != NULL) {
        ((void (*)(id, SEL, BOOL))original)(self, _cmd, NO);
    }
}

static void ForceNoFlush(id self, SEL _cmd, BOOL value) {
    (void)value;
    IMP original = LoadOriginal(&gOriginalSetNeedFlushIP);
    if (original != NULL) {
        ((void (*)(id, SEL, BOOL))original)(self, _cmd, NO);
    }
}

static void PatchedAlertHandler(id self, SEL _cmd, id alert, NSInteger buttonIndex) {
    NSString *title = ObjectProperty(alert, @selector(title)) ?: @"";
    if ([title containsString:@"捐赠码"] || [title containsString:@"捐赠"]) {
        return;
    }
    IMP original = LoadOriginal(&gOriginalAlertHandler);
    if (original != NULL) {
        ((void (*)(id, SEL, id, NSInteger))original)(
            self,
            _cmd,
            alert,
            buttonIndex
        );
    }
}

static void PatchedViewDidLoad(id self, SEL _cmd) {
    IMP original = LoadOriginal(&gOriginalViewDidLoad);
    if (original != NULL) {
        ((void (*)(id, SEL))original)(self, _cmd);
    }
    RepairController(self);
}

static void PatchedUpdateUITimer(id self, SEL _cmd) {
    IMP original = LoadOriginal(&gOriginalUpdateUITimer);
    if (original != NULL) {
        ((void (*)(id, SEL))original)(self, _cmd);
    }
    RepairController(self);
}

static void PatchedLabelSetText(UILabel *label, SEL _cmd, NSString *text) {
    NSString *replacement = text;
    if ([text isEqualToString:@"正在适配网络节点..."]) {
        replacement = @"网络节点已就绪";
    } else if ([text isEqualToString:@"测试权限:(null)"]) {
        replacement = @"测试权限:永久";
    }

    IMP original = LoadOriginal(&gOriginalLabelSetText);
    if (original != NULL) {
        ((void (*)(id, SEL, id))original)(label, _cmd, replacement);
    }
}

static BOOL InstallLabelPatch(void) {
    Method method = class_getInstanceMethod([UILabel class], @selector(setText:));
    if (method == NULL) {
        return NO;
    }
    IMP replacement = (IMP)PatchedLabelSetText;
    IMP current = method_getImplementation(method);
    if (current == replacement) {
        return YES;
    }

    IMP original = LoadOriginal(&gOriginalLabelSetText);
    if (original == NULL) {
        StoreOriginalOnce(&gOriginalLabelSetText, current);
        original = LoadOriginal(&gOriginalLabelSetText);
    }
    if (current != original) {
        return NO;
    }
    method_setImplementation(method, replacement);
    return method_getImplementation(method) == replacement;
}

static BOOL ReplaceExpected(
    Class cls,
    const char *selectorName,
    uintptr_t expectedOffset,
    IMP replacement,
    _Atomic(uintptr_t) *originalStorage
) {
    SEL selector = sel_registerName(selectorName);
    Method method = class_getInstanceMethod(cls, selector);
    if (method == NULL) {
        return NO;
    }

    IMP current = method_getImplementation(method);
    if (current == replacement) {
        return YES;
    }

    Dl_info imageInfo = {0};
    if (dladdr((const void *)current, &imageInfo) == 0 ||
        imageInfo.dli_fbase == NULL ||
        imageInfo.dli_fname == NULL ||
        strstr(imageInfo.dli_fname, "/CTW Pro") == NULL) {
        return NO;
    }
    uintptr_t currentOffset = (uintptr_t)current - (uintptr_t)imageInfo.dli_fbase;
    if (currentOffset != expectedOffset) {
        return NO;
    }

    if (originalStorage != NULL) {
        StoreOriginalOnce(originalStorage, current);
    }
    method_setImplementation(method, replacement);
    return method_getImplementation(method) == replacement;
}

static BOOL InstallRuntimePatches(void) {
    Class viewController = objc_getClass("ViewController");
    if (viewController == Nil) {
        return NO;
    }

    BOOL complete = InstallLabelPatch();
    complete &= ReplaceExpected(viewController, "viewDidLoad", 0x5025c0,
                                (IMP)PatchedViewDidLoad, &gOriginalViewDidLoad);
    complete &= ReplaceExpected(viewController, "updateUITimer", 0x515af0,
                                (IMP)PatchedUpdateUITimer, &gOriginalUpdateUITimer);
    complete &= ReplaceExpected(viewController, "alertView:clickedButtonAtIndex:", 0x50c684,
                                (IMP)PatchedAlertHandler, &gOriginalAlertHandler);
    complete &= ReplaceExpected(viewController, "recharge:", 0x557bc0,
                                (IMP)NoopAction, NULL);
    complete &= ReplaceExpected(viewController, "showQRCodeView:", 0x4dccb0,
                                (IMP)NoopAction, NULL);
    complete &= ReplaceExpected(viewController, "scanQRCode:", 0x4e1c8c,
                                (IMP)NoopAction, NULL);
    complete &= ReplaceExpected(viewController, "qrCodeScannerDidScanResult:", 0x4e2530,
                                (IMP)NoopAction, NULL);
    complete &= ReplaceExpected(
        viewController,
        "JvgnSRHcrHmZxNJocXZHWQYSFjPrglVHvpybVYfpfuMZRgoCejVYdqxxTCjtzbfDwaNkQ",
        0x4e6700,
        (IMP)NoopVoid,
        NULL
    );
    complete &= ReplaceExpected(viewController, "lockUI:", 0x557560,
                                (IMP)NoopAction, NULL);
    complete &= ReplaceExpected(viewController, "isNeedCheckIP", 0x56cfb0,
                                (IMP)AlwaysNo, NULL);
    complete &= ReplaceExpected(viewController, "setIsNeedCheckIP:", 0x56d67c,
                                (IMP)ForceNoCheck, &gOriginalSetNeedCheckIP);
    complete &= ReplaceExpected(viewController, "isNeedFlushIP", 0x56dd44,
                                (IMP)AlwaysNo, NULL);
    complete &= ReplaceExpected(viewController, "setIsNeedFlushIP:", 0x56e438,
                                (IMP)ForceNoFlush, &gOriginalSetNeedFlushIP);
    return complete;
}

static void *PatchWorker(void *context) {
    (void)context;
    BOOL complete = NO;
    for (;;) {
        @autoreleasepool {
            complete = InstallRuntimePatches();
        }
        usleep(complete ? 250000 : 5000);
    }
    return NULL;
}

__attribute__((constructor))
static void CTWProDeepPatchInitialize(void) {
    pthread_t worker;
    if (pthread_create(&worker, NULL, PatchWorker, NULL) == 0) {
        pthread_detach(worker);
    }
}
