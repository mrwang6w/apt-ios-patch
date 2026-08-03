#import <Foundation/Foundation.h>
#import <UIKit/UIKit.h>
#import <dlfcn.h>
#import <errno.h>
#import <objc/runtime.h>
#import <signal.h>
#import <stdatomic.h>
#import <stdint.h>
#import <stdlib.h>
#import <string.h>
#import <unistd.h>

extern int proc_listpids(
    uint32_t type,
    uint32_t typeinfo,
    void *buffer,
    int buffersize
);
extern int proc_pidpath(int pid, void *buffer, uint32_t buffersize);

#define CTW_PROC_ALL_PIDS 1

static _Atomic(uintptr_t) gOriginalViewDidLoad;
static _Atomic(uintptr_t) gOriginalUpdateUITimer;
static _Atomic(uintptr_t) gOriginalAlertHandler;
static _Atomic(uintptr_t) gOriginalSetNeedCheckIP;
static _Atomic(uintptr_t) gOriginalSetNeedFlushIP;
static _Atomic(uintptr_t) gOriginalMachineModelInit;
static id gCapturedMachineModel;
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

static BOOL CallVoid(id receiver, const char *selectorName) {
    if (receiver == nil) {
        return NO;
    }
    SEL selector = sel_registerName(selectorName);
    if (![receiver respondsToSelector:selector]) {
        return NO;
    }
    IMP implementation = [receiver methodForSelector:selector];
    ((void (*)(id, SEL))implementation)(receiver, selector);
    return YES;
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

static Class LoadDeviceConfigClass(NSString **failureStage) {
    Class configClass = objc_getClass("LKDeviceConfig");
    if (configClass != Nil) {
        return configClass;
    }

    static const char *paths[] = {
        "/var/jb/Library/MobileSubstrate/DynamicLibraries/CTW.dylib",
        "/Library/MobileSubstrate/DynamicLibraries/CTW.dylib"
    };
    BOOL loadedImage = NO;
    for (NSUInteger index = 0; index < sizeof(paths) / sizeof(paths[0]); index++) {
        void *handle = dlopen(paths[index], RTLD_NOW | RTLD_GLOBAL);
        if (handle == NULL) {
            continue;
        }
        loadedImage = YES;
        configClass = objc_getClass("LKDeviceConfig");
        if (configClass != Nil) {
            return configClass;
        }
    }

    *failureStage = loadedImage ? @"config-class" : @"config-dlopen";
    return Nil;
}

static NSDictionary *BuildLocalRandomConfig(NSString **failureStage) {
    Class configClass = LoadDeviceConfigClass(failureStage);
    if (configClass == Nil) {
        return nil;
    }
    SEL sharedSelector = sel_registerName("sharedInstance");
    if (![(id)configClass respondsToSelector:sharedSelector]) {
        *failureStage = @"config-shared-selector";
        return nil;
    }

    *failureStage = @"config-shared-instance";
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
        config[@"active"] = @1;
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

static id CapturingMachineModelInit(id self, SEL _cmd) {
    IMP original = LoadOriginal(&gOriginalMachineModelInit);
    if (original == NULL) {
        return nil;
    }
    id model = ((id (*)(id, SEL))original)(self, _cmd);
    gCapturedMachineModel = model;
    return model;
}

static BOOL InstallMachineModelCapture(Class dataClass) {
    SEL selector = @selector(init);
    Method method = class_getInstanceMethod(dataClass, selector);
    if (method == NULL) {
        return NO;
    }

    IMP replacement = (IMP)CapturingMachineModelInit;
    IMP current = method_getImplementation(method);
    if (current == replacement) {
        return LoadOriginal(&gOriginalMachineModelInit) != NULL;
    }
    if (LoadOriginal(&gOriginalMachineModelInit) != NULL) {
        return NO;
    }

    StoreOriginalOnce(&gOriginalMachineModelInit, current);
    const char *types = method_getTypeEncoding(method);
    if (types == NULL ||
        !class_addMethod(dataClass, selector, replacement, types)) {
        return NO;
    }
    return method_getImplementation(
        class_getInstanceMethod(dataClass, selector)
    ) == replacement;
}

static id CaptureNativeMachineModel(
    id preferences,
    id sender,
    NSString **failureStage
) {
    Class dataClass = objc_getClass(
        "XOOzsMKFjKOTTWpGaSiRovjOEBkIbziXWYeTFbNowILLPbtrlKiQXgHNTzcsEDDcOTqJQ"
    );
    if (dataClass == Nil) {
        *failureStage = @"model-class";
        return nil;
    }

    IMP nativeImplementation = ExpectedMainImplementation(
        [preferences class],
        "nativePreferences:",
        0x88254
    );
    if (nativeImplementation == NULL) {
        *failureStage = @"native-contract";
        return nil;
    }

    @try {
        ((void (*)(id, SEL, id))nativeImplementation)(
            preferences,
            sel_registerName("nativePreferences:"),
            sender
        );
    } @catch (__unused NSException *exception) {
        *failureStage = @"native-call";
        return nil;
    }

    id model = gCapturedMachineModel;
    if (model == nil || ![model isKindOfClass:dataClass]) {
        *failureStage = @"model-capture";
        return nil;
    }
    return model;
}

static BOOL ApplyRandomModelValues(
    id preferences,
    id model,
    NSDictionary *config,
    NSString **failureStage
) {
    NSString *machine = config[@"machine"];
    NSString *mode = config[@"mode"];
    NSString *random = config[@"random"];
    NSString *udid = config[@"udid"];
    NSString *serialNumber = config[@"serial_number"];
    NSString *mac = config[@"mac"];
    NSString *systemVersion = config[@"system_version"];
    NSString *unknownNumber = [config[@"unknownNumber"] stringValue];
    if (unknownNumber.length > 15) {
        unknownNumber = [unknownNumber substringToIndex:15];
    }
    if (model == nil || machine.length == 0 || mode.length == 0 ||
        random.length == 0 || udid.length == 0 || serialNumber.length == 0 ||
        mac.length == 0 || systemVersion.length == 0 ||
        unknownNumber.length == 0) {
        *failureStage = @"model-values";
        return NO;
    }

    NSArray<NSDictionary *> *carriers = @[
        @{
            @"name": @"中国移动", @"mcc": @"460", @"mnc": @"00",
            @"radio": @"CTRadioAccessTechnologyLTE"
        },
        @{
            @"name": @"中国联通", @"mcc": @"460", @"mnc": @"01",
            @"radio": @"CTRadioAccessTechnologyLTE"
        },
        @{
            @"name": @"中国电信", @"mcc": @"460", @"mnc": @"03",
            @"radio": @"CTRadioAccessTechnologyLTE"
        }
    ];
    NSDictionary *carrier = carriers[
        arc4random_uniform((uint32_t)carriers.count)
    ];
    NSString *uuid = [NSUUID UUID].UUIDString;
    NSString *idfa = [NSUUID UUID].UUIDString;
    NSString *suffix = [random substringToIndex:MIN((NSUInteger)6, random.length)];
    uint32_t subnet = arc4random_uniform(250) + 2;
    uint32_t host = arc4random_uniform(250) + 2;

    @try {
        NSDictionary<NSString *, id> *values = @{
            @"control": @1,
            @"mcdata": machine,
            @"HqWSUyrjbTUzCPTazXvClMsmRtTfgqkGkEvfqppATSWkzaHNNLPWHjKAzgCneDvTzjDlQPmA": udid,
            @"bqxafqLuDXtlLKFqRbPMxgliYzwnXuSFMenOjvRrfimIhaKOqiHedZNsPwLctqbxkpfg": serialNumber,
            @"IQvOpDvTZnSCwoCBHSQZwlQkQdLYNjiGGsGZQeqQQyUlfnyeQGHxWoOMUpvyQcKEYLtrDA": unknownNumber,
            @"NYwvVoabtQxxrAaNZcZLxjEnzDxWUrZBMXpvQIJlnhemIFuBYkCUpEWyMmyjyNYg": [@"iPhone-" stringByAppendingString:suffix.uppercaseString],
            @"WaVtzcpxylDkuyLRkDnABdUIQVIfehkltuPHCuRteQsSpiivERZurxDemNNnFjqbLSJrdDmnGw": mode,
            @"domain": machine,
            @"sbXrnbPhJnwudayxwwOfBvhAzfzBuHmWjnZsXtZNvZrfshIccKDzVYzghyUAirwmKuhzObA": machine,
            @"identifierForVendor": uuid,
            @"advertisingIdentifier": idfa,
            @"jNQIGodfXDzOKALLzABzIGQYakInudUHTsQBYzYfiATwKfHSIILgMpEBDHecfaBgA": [@"WiFi-" stringByAppendingString:suffix.uppercaseString],
            @"maLJLLPwAZVHkkbkRRqHrrdyxsJPkoPEZCbipLJsAWpIjsVCSyZgENgsFwnWjuFjabrwdgQ": mac,
            @"cLZdCrrDMbyysKCAOXEwMJSseimwdwLjwqsWVaXiExElYOsxraTZLUIcanTErEzJexCwEww": mac,
            @"cczmztMdiHXMVRwefgbiCrSwywunGbCUsgoaNYVhaIidwVcZqCGKfZlBEGMlcXhetxmKkrPnhjAQ": [NSString stringWithFormat:@"192.168.%u.1", subnet],
            @"KZLRCaLvYTCFuHfSqaDrxrxkedkBvJKNlgZnXDeTSRCtUMhsPBskwLenHeezPpagxpKg": [NSString stringWithFormat:@"192.168.%u.%u", subnet, host],
            @"brightness": @((arc4random_uniform(81) + 15) / 100.0),
            @"uUojPBFHpzwBfxnlMnifHEeTTXtnIEnelcdrpUgJhvZOGoDfZfasVhAtpyGkCGCJoiUA": @((arc4random_uniform(51) + 50) / 100.0),
            @"GOcuqPfvHaENZkclImuXKUbaOEHHaePFSfNIIiLcvQNmVczGtXJhSEEENnrvEyIHATbQ": @(arc4random_uniform(3) + 1),
            @"twhuxDfnZWriUzkpYMZUEuuVzSexOPLOYuTqbFVsumbfphSYxwuraqwBxFmAWMSSLdSkdUlYA": systemVersion,
            @"carrierName": carrier[@"name"],
            @"carrierNameDisplay": carrier[@"name"],
            @"mobileCountryCode": carrier[@"mcc"],
            @"mobileNetworkCode": carrier[@"mnc"],
            @"isoCountryCode": @"cn",
            @"radioAccessTechnology": carrier[@"radio"],
            @"MIEMhxTVAGouTqlnGbKAvNMLvhtNFAGOZzfhMKSsNvRbjEvIqCDGeHShCCvUSSQbuQw": @"WIFI"
        };
        for (NSString *key in values) {
            [model setValue:values[key] forKey:key];
        }
    } @catch (__unused NSException *exception) {
        *failureStage = @"model-write";
        return NO;
    }

    CallVoidBool(preferences, "setIsNative:", YES);
    if (!CallVoid((id)objc_getClass("MachinePreferences"), "save")) {
        *failureStage = @"model-save";
        return NO;
    }
    CallVoid(CallObject(preferences, "tableView"), "reloadData");
    return YES;
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

static BOOL IsAllowedContainerPath(NSString *path) {
    if (![path isKindOfClass:[NSString class]]) {
        return NO;
    }
    NSString *standard = path.stringByStandardizingPath;
    static NSArray<NSString *> *prefixes;
    static dispatch_once_t onceToken;
    dispatch_once(&onceToken, ^{
        prefixes = @[
            @"/private/var/mobile/Containers/Data/Application/",
            @"/private/var/mobile/Containers/Shared/AppGroup/",
            @"/private/var/mobile/Containers/Data/PluginKitPlugin/",
            @"/var/mobile/Containers/Data/Application/",
            @"/var/mobile/Containers/Shared/AppGroup/",
            @"/var/mobile/Containers/Data/PluginKitPlugin/"
        ];
    });
    for (NSString *prefix in prefixes) {
        if (![standard hasPrefix:prefix]) {
            continue;
        }
        NSString *leaf = [standard substringFromIndex:prefix.length];
        return leaf.length > 0 && [leaf rangeOfString:@"/"].location == NSNotFound;
    }
    return NO;
}

static void ClearContainerContents(
    NSString *path,
    NSMutableArray<NSString *> *errors
) {
    if (!IsAllowedContainerPath(path)) {
        [errors addObject:[NSString stringWithFormat:@"拒绝异常容器路径: %@", path ?: @"(null)"]];
        return;
    }

    NSFileManager *manager = [NSFileManager defaultManager];
    BOOL isDirectory = NO;
    if (![manager fileExistsAtPath:path isDirectory:&isDirectory] || !isDirectory) {
        [errors addObject:[NSString stringWithFormat:@"容器不存在: %@", path]];
        return;
    }

    NSError *listError = nil;
    NSArray<NSString *> *items = [manager contentsOfDirectoryAtPath:path
                                                              error:&listError];
    if (items == nil) {
        [errors addObject:[NSString stringWithFormat:
            @"读取容器失败: %@ (%@)", path, listError.localizedDescription ?: @"unknown"
        ]];
        return;
    }

    for (NSString *item in items) {
        if ([item isEqualToString:@".com.apple.mobile_container_manager.metadata.plist"]) {
            continue;
        }
        NSString *child = [path stringByAppendingPathComponent:item];
        NSError *removeError = nil;
        if (![manager removeItemAtPath:child error:&removeError]) {
            [errors addObject:[NSString stringWithFormat:
                @"删除失败: %@ (%@)", child,
                removeError.localizedDescription ?: @"unknown"
            ]];
        }
    }
}

static void TerminateExecutable(
    NSString *executable,
    NSMutableArray<NSString *> *errors
) {
    if (![executable isKindOfClass:[NSString class]] || executable.length == 0) {
        [errors addObject:@"目标 App 缺少 exec 字段"];
        return;
    }

    int bytes = proc_listpids(CTW_PROC_ALL_PIDS, 0, NULL, 0);
    if (bytes <= 0) {
        [errors addObject:[NSString stringWithFormat:@"无法枚举进程: %@", executable]];
        return;
    }
    bytes += (int)(32 * sizeof(int));
    int *pids = calloc(1, (size_t)bytes);
    if (pids == NULL) {
        [errors addObject:@"进程枚举内存不足"];
        return;
    }

    int used = proc_listpids(CTW_PROC_ALL_PIDS, 0, pids, bytes);
    int count = MAX(used, 0) / (int)sizeof(int);
    for (int index = 0; index < count; index++) {
        int pid = pids[index];
        if (pid <= 1 || pid == getpid()) {
            continue;
        }
        char pathBuffer[4096] = {0};
        if (proc_pidpath(pid, pathBuffer, sizeof(pathBuffer)) <= 0) {
            continue;
        }
        NSString *processPath = [NSString stringWithUTF8String:pathBuffer];
        if (![processPath.lastPathComponent isEqualToString:executable]) {
            continue;
        }
        if (kill(pid, SIGKILL) != 0 && errno != ESRCH) {
            [errors addObject:[NSString stringWithFormat:
                @"终止 %@ 失败: %s", executable, strerror(errno)
            ]];
        }
    }
    free(pids);
}

static void LocalApplyMachine(id self, SEL _cmd) {
    (void)_cmd;
    if (![NSThread isMainThread]) {
        dispatch_async(dispatch_get_main_queue(), ^{
            LocalApplyMachine(self, sel_registerName("performeMachineStub"));
        });
        return;
    }

    NSMutableArray<NSString *> *errors = [NSMutableArray array];
    NSUserDefaults *defaults = [NSUserDefaults standardUserDefaults];
    id applyValue = [defaults objectForKey:@"Applylist"];
    NSArray *applications = [applyValue isKindOfClass:[NSArray class]]
        ? applyValue : nil;
    NSDictionary *settings = [[defaults objectForKey:@"SettingsBackup"]
        isKindOfClass:[NSDictionary class]]
        ? [defaults objectForKey:@"SettingsBackup"] : @{};
    if (applications.count == 0) {
        [errors addObject:@"没有选中的 App"];
    }

    for (id value in applications) {
        if (![value isKindOfClass:[NSDictionary class]]) {
            [errors addObject:@"Applylist 包含异常记录"];
            continue;
        }
        TerminateExecutable(value[@"exec"], errors);
    }
    if (applications.count > 0) {
        usleep(200000);
    }

    if ([settings[@"ContainerRebuild"] boolValue]) {
        for (NSDictionary *application in applications) {
            if (![application isKindOfClass:[NSDictionary class]]) {
                continue;
            }
            ClearContainerContents(application[@"container"], errors);

            id groupsValue = application[@"groupContainers"];
            if ([groupsValue isKindOfClass:[NSDictionary class]]) {
                for (id groupPath in [groupsValue allValues]) {
                    ClearContainerContents(groupPath, errors);
                }
            }

            id pluginsValue = application[@"pluginDataContainers"];
            if ([pluginsValue isKindOfClass:[NSArray class]]) {
                for (id pluginValue in pluginsValue) {
                    if (![pluginValue isKindOfClass:[NSDictionary class]]) {
                        [errors addObject:@"插件容器记录异常"];
                        continue;
                    }
                    ClearContainerContents(pluginValue[@"path"], errors);
                }
            }
        }
    }

    if ([settings[@"ClearPB"] boolValue]) {
        [UIPasteboard generalPasteboard].items = @[];
    }

    RepairController(self);
    if ([self isKindOfClass:[UIViewController class]] && errors.count > 0) {
        NSString *message = [errors componentsJoinedByString:@"\n"];
        UIAlertController *alert = [UIAlertController
            alertControllerWithTitle:@"本地抹机未完整完成"
                             message:message
                      preferredStyle:UIAlertControllerStyleAlert];
        [alert addAction:[UIAlertAction actionWithTitle:@"确认"
                                                 style:UIAlertActionStyleDefault
                                               handler:nil]];
        [(UIViewController *)self presentViewController:alert
                                               animated:YES
                                             completion:nil];
    } else {
        UILabel *status = ObjectProperty(self, @selector(statusDescription));
        if ([status isKindOfClass:[UILabel class]]) {
            status.text = @"本地新机已完成";
        }
    }
}

static void LocalRandomPreferences(id self, SEL _cmd, id sender) {
    (void)_cmd;
    if (![self isKindOfClass:[UIViewController class]]) {
        return;
    }

    UIViewController *preferences = (UIViewController *)self;
    NSString *failureStage = nil;
    id model = CaptureNativeMachineModel(self, sender, &failureStage);
    if (model == nil) {
        if ([sender respondsToSelector:@selector(setEnabled:)]) {
            [sender setEnabled:YES];
        }
        ShowOfflineRandomError(preferences, failureStage);
        return;
    }

    NSDictionary *config = BuildLocalRandomConfig(&failureStage);
    if (config == nil ||
        !ApplyRandomModelValues(self, model, config, &failureStage)) {
        if ([sender respondsToSelector:@selector(setEnabled:)]) {
            [sender setEnabled:YES];
        }
        ShowOfflineRandomError(preferences, failureStage);
        return;
    }

    if ([sender respondsToSelector:@selector(setEnabled:)]) {
        [sender setEnabled:YES];
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
    Class machineModel = objc_getClass(
        "XOOzsMKFjKOTTWpGaSiRovjOEBkIbziXWYeTFbNowILLPbtrlKiQXgHNTzcsEDDcOTqJQ"
    );
    if (viewController == Nil || machinePreferences == Nil ||
        machineModel == Nil) {
        return NO;
    }

    BOOL complete = InstallLabelPatch();
    complete &= InstallMachineModelCapture(machineModel);
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
    complete &= ReplaceExpected(viewController, "performeMachineStub", 0x53de04,
                                (IMP)LocalApplyMachine, NULL);
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
