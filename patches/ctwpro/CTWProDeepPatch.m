#import <Foundation/Foundation.h>
#import <UIKit/UIKit.h>
#import <CommonCrypto/CommonCryptor.h>
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

typedef struct {
    const char *machine;
    const char *mode;
    const char *width;
    const char *height;
    uint64_t memoryBytes;
    uint64_t storageBytes;
} CTWModelProfile;

typedef struct {
    const char *version;
    const char *build;
    const char *webkitVersion;
} CTWSystemProfile;

static const CTWModelProfile kCompatibleModelProfiles[] = {
    {"iPhone9,1", "D10AP", "750", "1334", 2097807360ULL, 127968497664ULL},
    {"iPhone9,2", "D11AP", "1242", "2208", 3144810496ULL, 127968497664ULL},
    {"iPhone9,3", "D101AP", "750", "1334", 2097807360ULL, 127968497664ULL},
    {"iPhone9,4", "D111AP", "1242", "2208", 3144810496ULL, 127968497664ULL},
};

static const CTWSystemProfile kCompatibleSystemProfiles[] = {
    {"15.8.4", "19H390", "15_8_4"},
    {"15.8.5", "19H394", "15_8_5"},
};

static NSString *const kCompatibleKernelVersion = @"21.6.0";
static NSString *const kCompatibleDarwinVersion =
    @"Darwin Kernel Version 21.6.0: Sun Oct 15 00:18:06 PDT 2023; "
     "root:xnu-8020.241.42~8/RELEASE_ARM64_T8010";

static NSString *ProfileString(const char *value) {
    return value == NULL ? nil : [NSString stringWithUTF8String:value];
}

static BOOL CompatibleProfilesAreValid(void) {
    static BOOL valid;
    static dispatch_once_t onceToken;
    dispatch_once(&onceToken, ^{
        NSMutableSet<NSString *> *machines = [NSMutableSet set];
        NSMutableSet<NSString *> *versions = [NSMutableSet set];
        valid = sizeof(kCompatibleModelProfiles) /
                    sizeof(kCompatibleModelProfiles[0]) >= 2 &&
                sizeof(kCompatibleSystemProfiles) /
                    sizeof(kCompatibleSystemProfiles[0]) >= 2;
        for (NSUInteger index = 0;
             valid && index < sizeof(kCompatibleModelProfiles) /
                                sizeof(kCompatibleModelProfiles[0]);
             index++) {
            const CTWModelProfile *profile = &kCompatibleModelProfiles[index];
            NSString *machine = ProfileString(profile->machine);
            valid = machine.length > 0 && ProfileString(profile->mode).length > 0 &&
                    ProfileString(profile->width).length > 0 &&
                    ProfileString(profile->height).length > 0 &&
                    profile->memoryBytes > 0 &&
                    profile->storageBytes > profile->memoryBytes &&
                    ![machines containsObject:machine];
            if (valid) {
                [machines addObject:machine];
            }
        }
        for (NSUInteger index = 0;
             valid && index < sizeof(kCompatibleSystemProfiles) /
                                sizeof(kCompatibleSystemProfiles[0]);
             index++) {
            const CTWSystemProfile *profile = &kCompatibleSystemProfiles[index];
            NSString *version = ProfileString(profile->version);
            valid = version.length > 0 && ProfileString(profile->build).length > 0 &&
                    ProfileString(profile->webkitVersion).length > 0 &&
                    ![versions containsObject:version];
            if (valid) {
                [versions addObject:version];
            }
        }
    });
    return valid;
}

static NSUInteger RandomIndexExcluding(NSUInteger count, NSInteger excluded) {
    if (excluded < 0 || (NSUInteger)excluded >= count) {
        return arc4random_uniform((uint32_t)count);
    }
    NSUInteger index = arc4random_uniform((uint32_t)(count - 1));
    return index >= (NSUInteger)excluded ? index + 1 : index;
}

static NSInteger ModelProfileIndex(NSString *machine) {
    for (NSUInteger index = 0;
         index < sizeof(kCompatibleModelProfiles) /
                     sizeof(kCompatibleModelProfiles[0]);
         index++) {
        if ([machine isEqualToString:ProfileString(
                kCompatibleModelProfiles[index].machine)]) {
            return (NSInteger)index;
        }
    }
    return NSNotFound;
}

static NSInteger SystemProfileIndex(NSString *version) {
    for (NSUInteger index = 0;
         index < sizeof(kCompatibleSystemProfiles) /
                     sizeof(kCompatibleSystemProfiles[0]);
         index++) {
        if ([version isEqualToString:ProfileString(
                kCompatibleSystemProfiles[index].version)]) {
            return (NSInteger)index;
        }
    }
    return NSNotFound;
}

static NSString *WebKitUserAgent(const CTWSystemProfile *profile) {
    return [NSString stringWithFormat:
        @"Mozilla/5.0 (iPhone; CPU iPhone OS %s like Mac OS X) "
         "AppleWebKit/605.1.15 (KHTML, like Gecko) Mobile/15E148",
        profile->webkitVersion
    ];
}

static NSString *RandomLinkLocalIPv6(void) {
    return [NSString stringWithFormat:@"fe80::%x:%x:%x:%x",
        arc4random_uniform(0x10000), arc4random_uniform(0x10000),
        arc4random_uniform(0x10000), arc4random_uniform(0x10000)];
}

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

static BOOL DisableLocalDeviceConfigOverrides(Class configClass) {
    static const struct {
        const char *selector;
        uintptr_t offset;
    } contracts[] = {
        {"_setupConfig", 0xb8f4},
        {"saveActivedConfig", 0xbf80},
    };
    Method methods[sizeof(contracts) / sizeof(contracts[0])] = {0};
    IMP replacement = (IMP)NoopVoid;
    for (NSUInteger index = 0;
         index < sizeof(contracts) / sizeof(contracts[0]);
         index++) {
        Method method = class_getInstanceMethod(
            configClass,
            sel_registerName(contracts[index].selector)
        );
        if (method == NULL) {
            return NO;
        }
        methods[index] = method;
        IMP current = method_getImplementation(method);
        if (current == replacement) {
            continue;
        }
        Dl_info imageInfo = {0};
        if (dladdr((const void *)current, &imageInfo) == 0 ||
            imageInfo.dli_fbase == NULL || imageInfo.dli_fname == NULL ||
            strstr(imageInfo.dli_fname, "/CTW.dylib") == NULL ||
            (uintptr_t)current - (uintptr_t)imageInfo.dli_fbase !=
                contracts[index].offset) {
            return NO;
        }
    }
    for (NSUInteger index = 0;
         index < sizeof(methods) / sizeof(methods[0]);
         index++) {
        method_setImplementation(methods[index], replacement);
        if (method_getImplementation(methods[index]) != replacement) {
            return NO;
        }
    }
    return YES;
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
        if (!DisableLocalDeviceConfigOverrides(configClass)) {
            *failureStage = @"config-setup-contract";
            return Nil;
        }
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
            if (!DisableLocalDeviceConfigOverrides(configClass)) {
                *failureStage = @"config-setup-contract";
                return Nil;
            }
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

        *failureStage = @"profile-data";
        if (!CompatibleProfilesAreValid()) {
            return nil;
        }
        NSUInteger modelCount = sizeof(kCompatibleModelProfiles) /
                                sizeof(kCompatibleModelProfiles[0]);
        NSUInteger systemCount = sizeof(kCompatibleSystemProfiles) /
                                 sizeof(kCompatibleSystemProfiles[0]);
        const CTWModelProfile *modelProfile = &kCompatibleModelProfiles[
            RandomIndexExcluding(
                modelCount,
                ModelProfileIndex(baseline[@"machine"])
            )
        ];
        const CTWSystemProfile *systemProfile = &kCompatibleSystemProfiles[
            RandomIndexExcluding(
                systemCount,
                SystemProfileIndex(baseline[@"system_version"])
            )
        ];
        NSString *machine = ProfileString(modelProfile->machine);
        NSString *mode = ProfileString(modelProfile->mode);
        NSString *systemVersion = ProfileString(systemProfile->version);
        NSString *webkit = WebKitUserAgent(systemProfile);
        if (machine.length == 0 || mode.length == 0 ||
            systemVersion.length == 0 || webkit.length == 0) {
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
        config[@"machine"] = machine;
        config[@"mode"] = mode;
        config[@"diskSize"] = @(modelProfile->memoryBytes);
        config[@"ncpu"] = @2;
        config[@"system"] = @"iOS";
        config[@"kern_version"] = kCompatibleKernelVersion;
        config[@"webkit"] = webkit;
        config[@"system_version"] = systemVersion;
        config[@"darwin"] = kCompatibleDarwinVersion;
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

        *failureStage = nil;
        return config;
    }
}

static BOOL PersistLocalRandomConfig(
    NSDictionary *config,
    NSString **failureStage
) {
    Class configClass = LoadDeviceConfigClass(failureStage);
    id instance = CallObject((id)configClass, "sharedInstance");
    if (instance == nil) {
        *failureStage = @"config-shared-instance";
        return NO;
    }

    NSError *error = nil;
    NSData *data = [NSJSONSerialization dataWithJSONObject:config
                                                   options:0
                                                     error:&error];
    NSString *json = data == nil ? nil : [[NSString alloc]
        initWithData:data encoding:NSUTF8StringEncoding];
    if (json == nil || error != nil) {
        *failureStage = @"serialize";
        return NO;
    }

    @synchronized (instance) {
        if (!CallBoolObject(instance, "writeCachedConfigString:", json)) {
            *failureStage = @"cache-write";
            return NO;
        }
        CallVoidObject(instance, "setConfig:", config);
        CallVoidBool(instance, "setDevice_updated:", YES);
    }
    *failureStage = nil;
    return YES;
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

typedef CCCryptorStatus (*CCCryptFunction)(
    CCOperation,
    CCAlgorithm,
    CCOptions,
    const void *,
    size_t,
    const void *,
    const void *,
    size_t,
    void *,
    size_t,
    size_t *
);

static NSString *AMGEncryptString(NSString *plainText) {
    if (![plainText isKindOfClass:[NSString class]]) {
        return nil;
    }

    CCCryptFunction crypt = (CCCryptFunction)dlsym(RTLD_DEFAULT, "CCCrypt");
    if (crypt == NULL) {
        return nil;
    }
    NSData *input = [plainText dataUsingEncoding:NSUTF8StringEncoding];
    if (input == nil) {
        return nil;
    }

    static const uint8_t key[kCCKeySizeAES128] = {
        'A', 'M', 'G', '2', '0', '1', '8'
    };
    size_t outputCapacity = input.length + kCCBlockSizeAES128;
    void *output = calloc(1, outputCapacity);
    if (output == NULL) {
        return nil;
    }

    size_t outputLength = 0;
    CCCryptorStatus status = crypt(
        kCCEncrypt,
        kCCAlgorithmAES,
        kCCOptionPKCS7Padding | kCCOptionECBMode,
        key,
        sizeof(key),
        NULL,
        input.bytes,
        input.length,
        output,
        outputCapacity,
        &outputLength
    );
    if (status != kCCSuccess) {
        free(output);
        return nil;
    }

    NSData *encrypted = [NSData dataWithBytesNoCopy:output
                                              length:outputLength
                                        freeWhenDone:YES];
    return [encrypted base64EncodedStringWithOptions:0];
}

static BOOL WriteAMGProfile(
    NSDictionary<NSString *, NSString *> *plainValues,
    NSString **failureStage
) {
    NSString *contract = AMGEncryptString(@"iPhone 17e");
    if (![contract isEqualToString:@"CZjs+FPhEmQb72XRMX7b9w=="]) {
        *failureStage = @"amg-crypto-contract";
        return NO;
    }

    NSString *path = @"/var/jb/var/mobile/Library/Preferences/AMG/faker.plist";
    NSMutableDictionary *profile = [NSMutableDictionary
        dictionaryWithContentsOfFile:path];
    if (profile == nil) {
        *failureStage = @"amg-profile-read";
        return NO;
    }

    NSMutableDictionary<NSString *, NSString *> *encryptedValues =
        [NSMutableDictionary dictionaryWithCapacity:plainValues.count];
    for (NSString *key in plainValues) {
        NSString *encrypted = AMGEncryptString(plainValues[key]);
        if (encrypted == nil) {
            *failureStage = @"amg-profile-encrypt";
            return NO;
        }
        encryptedValues[key] = encrypted;
        profile[key] = encrypted;
    }

    NSError *error = nil;
    NSData *serialized = [NSPropertyListSerialization
        dataWithPropertyList:profile
                      format:NSPropertyListXMLFormat_v1_0
                     options:0
                       error:&error];
    if (serialized == nil || error != nil) {
        *failureStage = @"amg-profile-serialize";
        return NO;
    }
    if (![serialized writeToFile:path
                         options:NSDataWritingAtomic
                           error:&error] || error != nil) {
        *failureStage = @"amg-profile-write";
        return NO;
    }

    NSDictionary *verified = [NSDictionary dictionaryWithContentsOfFile:path];
    for (NSString *key in encryptedValues) {
        if (![verified[key] isEqualToString:encryptedValues[key]]) {
            *failureStage = @"amg-profile-verify";
            return NO;
        }
    }
    return YES;
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
    NSInteger modelIndex = ModelProfileIndex(machine);
    NSInteger systemIndex = SystemProfileIndex(systemVersion);
    if (modelIndex == NSNotFound || systemIndex == NSNotFound) {
        *failureStage = @"model-profile";
        return NO;
    }
    const CTWModelProfile *modelProfile =
        &kCompatibleModelProfiles[(NSUInteger)modelIndex];
    const CTWSystemProfile *systemProfile =
        &kCompatibleSystemProfiles[(NSUInteger)systemIndex];
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
    NSString *idfv = [NSUUID UUID].UUIDString;
    NSString *idfa = [NSUUID UUID].UUIDString;
    NSString *suffix = [random substringToIndex:MIN((NSUInteger)6, random.length)];
    NSString *deviceName = [@"iPhone-" stringByAppendingString:suffix.uppercaseString];
    NSString *ssid = [@"WiFi-" stringByAppendingString:suffix.uppercaseString];
    NSString *deviceToken = [random stringByAppendingString:
        [udid substringToIndex:MIN((NSUInteger)24, udid.length)]];
    double brightness = (arc4random_uniform(81) + 15) / 100.0;
    uint32_t subnet = arc4random_uniform(250) + 2;
    uint32_t host = arc4random_uniform(250) + 2;

    @try {
        NSDictionary<NSString *, id> *values = @{
            @"control": @1,
            @"mcdata": machine,
            @"HqWSUyrjbTUzCPTazXvClMsmRtTfgqkGkEvfqppATSWkzaHNNLPWHjKAzgCneDvTzjDlQPmA": udid,
            @"bqxafqLuDXtlLKFqRbPMxgliYzwnXuSFMenOjvRrfimIhaKOqiHedZNsPwLctqbxkpfg": serialNumber,
            @"IQvOpDvTZnSCwoCBHSQZwlQkQdLYNjiGGsGZQeqQQyUlfnyeQGHxWoOMUpvyQcKEYLtrDA": unknownNumber,
            @"NYwvVoabtQxxrAaNZcZLxjEnzDxWUrZBMXpvQIJlnhemIFuBYkCUpEWyMmyjyNYg": deviceName,
            @"WaVtzcpxylDkuyLRkDnABdUIQVIfehkltuPHCuRteQsSpiivERZurxDemNNnFjqbLSJrdDmnGw": mode,
            @"build": ProfileString(systemProfile->build),
            @"domain": machine,
            @"model": @"iPhone",
            @"sbXrnbPhJnwudayxwwOfBvhAzfzBuHmWjnZsXtZNvZrfshIccKDzVYzghyUAirwmKuhzObA": machine,
            @"identifierForVendor": idfv,
            @"advertisingIdentifier": idfa,
            @"jNQIGodfXDzOKALLzABzIGQYakInudUHTsQBYzYfiATwKfHSIILgMpEBDHecfaBgA": ssid,
            @"maLJLLPwAZVHkkbkRRqHrrdyxsJPkoPEZCbipLJsAWpIjsVCSyZgENgsFwnWjuFjabrwdgQ": mac,
            @"cLZdCrrDMbyysKCAOXEwMJSseimwdwLjwqsWVaXiExElYOsxraTZLUIcanTErEzJexCwEww": mac,
            @"cczmztMdiHXMVRwefgbiCrSwywunGbCUsgoaNYVhaIidwVcZqCGKfZlBEGMlcXhetxmKkrPnhjAQ": [NSString stringWithFormat:@"192.168.%u.1", subnet],
            @"KZLRCaLvYTCFuHfSqaDrxrxkedkBvJKNlgZnXDeTSRCtUMhsPBskwLenHeezPpagxpKg": [NSString stringWithFormat:@"192.168.%u.%u", subnet, host],
            @"zpxUqMISNJWZLHlOBediVxXcdVUKrrmqXvSsMifSjFKYDoWjrvzDixnbpxPazLLQtXmbgiEnw": RandomLinkLocalIPv6(),
            @"FyUiDZGYamUMxCIztFXWObToSHjJKhwAjmfevOxwXuTZJLKeIYwcyFGcVLPhNfKILdMwHFGg": RandomLinkLocalIPv6(),
            @"WRWFKvOtwaEmWymaXsXNJurBExDTxJiSyWdHDRqKDphqnZaJvFzmXFGSigZzYLCTMuKZzvwZw": @(modelProfile->memoryBytes),
            @"UByrXfBwjMONBlVOksHDHDuTKiklVRXQGbzQauRwxZywikXAEtVMuCrFqmFWxVbapQ": @(modelProfile->storageBytes),
            @"wnXAAOsrwroZGyAduvxMPWBIQWSoiPOMveyZYDLdLbodPFGgTYnnvZDFMVcZYMpGhQZajiXQ": ProfileString(modelProfile->width),
            @"sElfHvGJordWkPBLWclpSrcMlRSTAUNaYUVsRTMTxTDSOJZeOMhxfBUANFdqFHvjrfoFlLA": ProfileString(modelProfile->height),
            @"brightness": @(brightness),
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
        [[NSUserDefaults standardUserDefaults] setObject:config[@"webkit"]
                                                  forKey:@"UA"];
    } @catch (__unused NSException *exception) {
        *failureStage = @"model-write";
        return NO;
    }

    CallVoidBool(preferences, "setIsNative:", YES);
    if (!CallVoid((id)objc_getClass("MachinePreferences"), "save")) {
        *failureStage = @"model-save";
        return NO;
    }
    if (!PersistLocalRandomConfig(config, failureStage)) {
        return NO;
    }
    if (deviceToken.length != 64 || !WriteAMGProfile(@{
        @"Model": machine,
        @"SystemVer": systemVersion,
        @"BuildVersion": ProfileString(systemProfile->build),
        @"Name": deviceName,
        @"Brightness": [NSString stringWithFormat:@"%.6f", brightness],
        @"UDID": udid,
        @"SerialNumber": serialNumber,
        @"IDFA": idfa,
        @"IDFV": idfv,
        @"WifiAddress": mac,
        @"BlueAddress": mac,
        @"BSSID": mac,
        @"SSID": ssid,
        @"DeviceToken": deviceToken
    }, failureStage)) {
        if (failureStage != NULL && *failureStage == nil) {
            *failureStage = @"amg-profile-values";
        }
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
