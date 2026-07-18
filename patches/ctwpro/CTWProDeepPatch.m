#import <Foundation/Foundation.h>
#import <UIKit/UIKit.h>
#import <dlfcn.h>
#import <objc/runtime.h>
#import <stdatomic.h>
#import <stdint.h>
#import <string.h>

static _Atomic(uintptr_t) gOriginalViewDidLoad;
static _Atomic(uintptr_t) gOriginalUpdateUITimer;
static _Atomic(uintptr_t) gOriginalAlertHandler;
static _Atomic(uintptr_t) gOriginalSetNeedCheckIP;
static _Atomic(uintptr_t) gOriginalSetNeedFlushIP;
static _Atomic(uintptr_t) gOriginalLabelSetText;

static id CallObject(id receiver, const char *selectorName) {
    if (receiver == nil) {
        return nil;
    }
    SEL selector = sel_registerName(selectorName);
    if (![receiver respondsToSelector:selector]) {
        return nil;
    }
    IMP implementation = [receiver methodForSelector:selector];
    return ((id (*)(id, SEL))implementation)(receiver, selector);
}

static id CallObjectUnsignedLongLong(
    id receiver,
    const char *selectorName,
    unsigned long long value
) {
    if (receiver == nil) {
        return nil;
    }
    SEL selector = sel_registerName(selectorName);
    if (![receiver respondsToSelector:selector]) {
        return nil;
    }
    IMP implementation = [receiver methodForSelector:selector];
    return ((id (*)(id, SEL, unsigned long long))implementation)(
        receiver,
        selector,
        value
    );
}

static void CallVoidObject(id receiver, const char *selectorName, id value) {
    if (receiver == nil) {
        return;
    }
    SEL selector = sel_registerName(selectorName);
    if (![receiver respondsToSelector:selector]) {
        return;
    }
    IMP implementation = [receiver methodForSelector:selector];
    ((void (*)(id, SEL, id))implementation)(receiver, selector, value);
}

static void CallVoidBool(id receiver, const char *selectorName, BOOL value) {
    if (receiver == nil) {
        return;
    }
    SEL selector = sel_registerName(selectorName);
    if (![receiver respondsToSelector:selector]) {
        return;
    }
    IMP implementation = [receiver methodForSelector:selector];
    ((void (*)(id, SEL, BOOL))implementation)(receiver, selector, value);
}

static BOOL CallBoolObject(id receiver, const char *selectorName, id value) {
    if (receiver == nil) {
        return NO;
    }
    SEL selector = sel_registerName(selectorName);
    if (![receiver respondsToSelector:selector]) {
        return NO;
    }
    IMP implementation = [receiver methodForSelector:selector];
    return ((BOOL (*)(id, SEL, id))implementation)(receiver, selector, value);
}

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

static BOOL IsCompleteLocalConfig(NSDictionary *config) {
    static NSSet<NSString *> *requiredKeys;
    static dispatch_once_t onceToken;
    dispatch_once(&onceToken, ^{
        requiredKeys = [NSSet setWithArray:@[
            @"random", @"machine", @"diskSize", @"serial_number", @"ncpu",
            @"unknownNumber", @"mac", @"system", @"kern_version", @"webkit",
            @"system_version", @"mode", @"active", @"boardSerial", @"darwin",
            @"udid", @"update_time"
        ]];
    });
    return [config isKindOfClass:[NSDictionary class]] &&
           [requiredKeys isSubsetOfSet:[NSSet setWithArray:config.allKeys]];
}

static BOOL IsUsableConfigBaseline(NSDictionary *config) {
    static NSSet<NSString *> *requiredKeys;
    static dispatch_once_t onceToken;
    dispatch_once(&onceToken, ^{
        requiredKeys = [NSSet setWithArray:@[
            @"machine", @"diskSize", @"ncpu", @"system", @"kern_version",
            @"webkit", @"system_version", @"mode", @"darwin"
        ]];
    });
    return [config isKindOfClass:[NSDictionary class]] &&
           [requiredKeys isSubsetOfSet:[NSSet setWithArray:config.allKeys]];
}

static NSDictionary *CachedConfigDictionary(id instance) {
    id cached = CallObject(instance, "readCachedConfigString");
    if (![cached isKindOfClass:[NSString class]]) {
        return nil;
    }
    NSData *data = [(NSString *)cached dataUsingEncoding:NSUTF8StringEncoding];
    if (data == nil) {
        return nil;
    }
    id object = [NSJSONSerialization JSONObjectWithData:data options:0 error:nil];
    return [object isKindOfClass:[NSDictionary class]] ? object : nil;
}

static NSDictionary *BuildLocalRandomConfig(NSString **failureStage) {
    *failureStage = @"config-instance";
    Class configClass = objc_getClass("LKDeviceConfig");
    id instance = CallObject((id)configClass, "sharedInstance");
    if (instance == nil) {
        return nil;
    }

    @synchronized (instance) {
        *failureStage = @"baseline";
        NSDictionary *baseline = CallObject(instance, "config");
        if (!IsUsableConfigBaseline(baseline)) {
            baseline = CachedConfigDictionary(instance);
        }
        if (!IsUsableConfigBaseline(baseline)) {
            baseline = CallObject(instance, "defaultConfig");
        }
        if (!IsUsableConfigBaseline(baseline)) {
            return nil;
        }

        *failureStage = @"random-helper";
        id random = CallObjectUnsignedLongLong(
            instance,
            "randomHexStringWithLength:",
            40
        );
        id udid = CallObjectUnsignedLongLong(
            instance,
            "randomHexStringWithLength:",
            40
        );
        id serialNumber = CallObjectUnsignedLongLong(
            instance,
            "randomAlphanumericStringWithLength:",
            12
        );
        id boardSerial = CallObjectUnsignedLongLong(
            instance,
            "randomAlphanumericStringWithLength:",
            16
        );
        id mac = CallObject(instance, "randomMacAddress");
        id unknownNumber = CallObject(instance, "randomUnknownNumber");
        if (random == nil || udid == nil || serialNumber == nil ||
            boardSerial == nil || mac == nil || unknownNumber == nil) {
            return nil;
        }

        NSMutableDictionary *config = [baseline mutableCopy];
        config[@"random"] = random;
        config[@"udid"] = udid;
        config[@"serial_number"] = serialNumber;
        config[@"boardSerial"] = boardSerial;
        config[@"mac"] = mac;
        config[@"unknownNumber"] = unknownNumber;
        config[@"active"] = @0;
        config[@"update_time"] = @([[NSDate date] timeIntervalSince1970]);
        *failureStage = @"final-config";
        if (!IsCompleteLocalConfig(config)) {
            return nil;
        }

        *failureStage = @"serialize";
        NSError *error = nil;
        NSData *data = [NSJSONSerialization dataWithJSONObject:config
                                                       options:0
                                                         error:&error];
        if (data == nil || error != nil) {
            return nil;
        }
        NSString *json = [[NSString alloc] initWithData:data
                                                encoding:NSUTF8StringEncoding];
        if (json == nil) {
            return nil;
        }

        *failureStage = @"cache-write";
        if (!CallBoolObject(instance, "writeCachedConfigString:", json)) {
            return nil;
        }
        CallVoidObject(instance, "setConfig:", config);
        CallVoidBool(instance, "setDevice_updated:", YES);
        *failureStage = nil;
        return config;
    }
}

static UIViewController *FindController(
    UIViewController *controller,
    Class targetClass
) {
    if (controller == nil) {
        return nil;
    }
    if ([controller isKindOfClass:targetClass]) {
        return controller;
    }
    if ([controller isKindOfClass:[UINavigationController class]]) {
        for (UIViewController *child in
             [(UINavigationController *)controller viewControllers].reverseObjectEnumerator) {
            UIViewController *match = FindController(child, targetClass);
            if (match != nil) {
                return match;
            }
        }
    }
    if ([controller isKindOfClass:[UITabBarController class]]) {
        UIViewController *match = FindController(
            [(UITabBarController *)controller selectedViewController],
            targetClass
        );
        if (match != nil) {
            return match;
        }
    }
    for (UIViewController *child in controller.childViewControllers) {
        UIViewController *match = FindController(child, targetClass);
        if (match != nil) {
            return match;
        }
    }
    return FindController(controller.presentedViewController, targetClass);
}

static UIViewController *FindMainViewController(UIViewController *preferences) {
    Class targetClass = objc_getClass("ViewController");
    if (targetClass == Nil) {
        return nil;
    }

    UIViewController *match = FindController(
        preferences.navigationController,
        targetClass
    );
    if (match != nil) {
        return match;
    }
    for (UIViewController *controller = preferences.parentViewController;
         controller != nil;
         controller = controller.parentViewController) {
        match = FindController(controller, targetClass);
        if (match != nil) {
            return match;
        }
    }
    for (UIViewController *controller = preferences.presentingViewController;
         controller != nil;
         controller = controller.presentingViewController) {
        match = FindController(controller, targetClass);
        if (match != nil) {
            return match;
        }
    }

    UIApplication *application = [UIApplication sharedApplication];
    UIWindow *preferencesWindow = preferences.viewIfLoaded.window;
    match = FindController(preferencesWindow.rootViewController, targetClass);
    if (match != nil) {
        return match;
    }
    UIWindow *delegateWindow = CallObject(application.delegate, "window");
    match = FindController(delegateWindow.rootViewController, targetClass);
    if (match != nil) {
        return match;
    }
    for (UIWindow *window in application.windows) {
        match = FindController(
            window.rootViewController,
            targetClass
        );
        if (match != nil) {
            return match;
        }
    }
    return nil;
}

static IMP ExpectedMainImplementation(
    Class cls,
    const char *selectorName,
    uintptr_t expectedOffset
) {
    Method method = class_getInstanceMethod(cls, sel_registerName(selectorName));
    if (method == NULL) {
        return NULL;
    }
    IMP implementation = method_getImplementation(method);
    Dl_info imageInfo = {0};
    if (dladdr((const void *)implementation, &imageInfo) == 0 ||
        imageInfo.dli_fbase == NULL || imageInfo.dli_fname == NULL ||
        strstr(imageInfo.dli_fname, "/CTW Pro") == NULL) {
        return NULL;
    }
    uintptr_t offset =
        (uintptr_t)implementation - (uintptr_t)imageInfo.dli_fbase;
    return offset == expectedOffset ? implementation : NULL;
}

static void ShowOfflineRandomError(
    UIViewController *controller,
    NSString *failureStage
) {
    NSString *message = [NSString stringWithFormat:
        @"失败阶段: %@\n未执行改机。",
        failureStage ?: @"unknown"
    ];
    UIAlertController *alert = [UIAlertController
        alertControllerWithTitle:@"离线新机生成失败"
                         message:message
                  preferredStyle:UIAlertControllerStyleAlert];
    [alert addAction:[UIAlertAction actionWithTitle:@"确认"
                                             style:UIAlertActionStyleDefault
                                           handler:nil]];
    [controller presentViewController:alert animated:YES completion:nil];
}

static void LocalRandomPreferences(id self, SEL _cmd, id sender) {
    (void)_cmd;
    if (![self isKindOfClass:[UIViewController class]]) {
        return;
    }

    UIViewController *preferences = (UIViewController *)self;
    UIViewController *mainController = FindMainViewController(preferences);
    if (mainController == nil) {
        if ([sender respondsToSelector:@selector(setEnabled:)]) {
            [sender setEnabled:YES];
        }
        ShowOfflineRandomError(preferences, @"controller");
        return;
    }

    Class mainClass = objc_getClass("ViewController");
    IMP applyImplementation = ExpectedMainImplementation(
        mainClass,
        "performeMachineStub",
        0x53de04
    );
    if (applyImplementation == NULL) {
        if ([sender respondsToSelector:@selector(setEnabled:)]) {
            [sender setEnabled:YES];
        }
        ShowOfflineRandomError(preferences, @"apply-contract");
        return;
    }

    NSString *failureStage = nil;
    if (BuildLocalRandomConfig(&failureStage) == nil) {
        if ([sender respondsToSelector:@selector(setEnabled:)]) {
            [sender setEnabled:YES];
        }
        ShowOfflineRandomError(preferences, failureStage);
        return;
    }

    if ([sender respondsToSelector:@selector(setEnabled:)]) {
        [sender setEnabled:NO];
    }

    void (^applyConfig)(void) = ^{
        RepairController(mainController);
        SEL selector = sel_registerName("performeMachineStub");
        ((void (*)(id, SEL))applyImplementation)(mainController, selector);
    };

    UINavigationController *navigationController =
        preferences.navigationController;
    if (navigationController != nil &&
        [navigationController.viewControllers containsObject:preferences] &&
        navigationController.viewControllers.count > 1) {
        [navigationController popViewControllerAnimated:YES];
        dispatch_after(
            dispatch_time(DISPATCH_TIME_NOW, 350 * NSEC_PER_MSEC),
            dispatch_get_main_queue(),
            applyConfig
        );
    } else if (preferences.presentingViewController != nil) {
        [preferences dismissViewControllerAnimated:YES completion:applyConfig];
    } else {
        applyConfig();
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
    Class machinePreferences = objc_getClass("MachinePreferences");
    if (viewController == Nil || machinePreferences == Nil) {
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
    complete &= ReplaceExpected(machinePreferences, "randomPreferences:",
                                0x84488, (IMP)LocalRandomPreferences, NULL);
    return complete;
}

static void SchedulePatchAttempt(void);

static void RunPatchAttempt(void) {
    @autoreleasepool {
        if (InstallRuntimePatches()) {
            return;
        }
    }
    SchedulePatchAttempt();
}

static void SchedulePatchAttempt(void) {
    dispatch_after(
        dispatch_time(DISPATCH_TIME_NOW, 50 * NSEC_PER_MSEC),
        dispatch_get_main_queue(),
        ^{
            RunPatchAttempt();
        }
    );
}

__attribute__((constructor))
static void CTWProDeepPatchInitialize(void) {
    dispatch_async(dispatch_get_main_queue(), ^{
        RunPatchAttempt();
    });
}
