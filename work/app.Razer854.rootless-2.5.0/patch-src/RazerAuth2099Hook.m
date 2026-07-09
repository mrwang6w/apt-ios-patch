#import <Foundation/Foundation.h>
#import <UIKit/UIKit.h>
#import <objc/runtime.h>
#import <objc/message.h>

static BOOL gRazerAuthHookEnabled = NO;
static NSString * const kRazerFutureText = @"2099.01.01 00:00";
static NSNumber *RZFutureTimestamp(void) { return @(4070880000LL); } // 2099-01-01 00:00:00 Asia/Shanghai

static BOOL RZIsTargetProcess(void) {
    NSBundle *bundle = [NSBundle mainBundle];
    NSString *bid = [bundle bundleIdentifier] ?: @"";
    NSString *exe = [[NSProcessInfo processInfo] processName] ?: @"";
    NSString *pathExe = [[bundle executablePath] lastPathComponent] ?: @"";
    return [bid isEqualToString:@"Razer"] || [exe isEqualToString:@"Razer"] || [pathExe isEqualToString:@"Razer"];
}

static BOOL RZKeyEquals(id key, NSString *s) {
    return [key isKindOfClass:[NSString class]] && [(NSString *)key isEqualToString:s];
}

static id RZForcedObjectForKey(id key, id originalValue) {
    if (!gRazerAuthHookEnabled || ![key isKindOfClass:[NSString class]]) return originalValue;
    NSString *k = (NSString *)key;
    if ([k isEqualToString:@"LicenseAccepted"]) return @YES;
    if ([k isEqualToString:@"ExpiredText"]) return kRazerFutureText;
    // Conservative aliases for expiry predicates seen in similar Razer/Zorro builds.
    NSString *lower = [k lowercaseString];
    if (([lower containsString:@"expire"] || [lower containsString:@"expiry"] || [lower containsString:@"deadline"] || [lower containsString:@"endtime"]) &&
        ([lower containsString:@"time"] || [lower containsString:@"date"] || [lower containsString:@"stamp"])) {
        return RZFutureTimestamp();
    }
    return originalValue;
}

static BOOL RZLooksLikeAuthAlertText(NSString *s) {
    if (![s isKindOfClass:[NSString class]] || s.length == 0) return NO;
    NSArray<NSString *> *needles = @[
        @"未授权", @"未授權", @"Unauthorized", @"unauthorized",
        @"请输入授权码", @"請輸入授權碼", @"Please Input LicenseCode", @"LicenseCode",
        @"license expired", @"授權碼", @"授权码"
    ];
    for (NSString *n in needles) {
        if ([s rangeOfString:n options:NSCaseInsensitiveSearch].location != NSNotFound) return YES;
    }
    return NO;
}

static NSString *RZSanitizedText(NSString *text) {
    if (![text isKindOfClass:[NSString class]]) return text;
    if ([text containsString:@"1970.01.01"] || [text containsString:@"1970-01-01"]) return kRazerFutureText;
    if ([text rangeOfString:@"未授权"].location != NSNotFound || [text rangeOfString:@"未授權"].location != NSNotFound ||
        [text rangeOfString:@"Unauthorized" options:NSCaseInsensitiveSearch].location != NSNotFound ||
        [text rangeOfString:@"license expired" options:NSCaseInsensitiveSearch].location != NSNotFound) {
        return kRazerFutureText;
    }
    return text;
}

@interface NSUserDefaults (RazerAuth2099Hook)
@end
@implementation NSUserDefaults (RazerAuth2099Hook)
- (id)rz2099_objectForKey:(NSString *)defaultName { return RZForcedObjectForKey(defaultName, [self rz2099_objectForKey:defaultName]); }
- (NSString *)rz2099_stringForKey:(NSString *)defaultName {
    id v = RZForcedObjectForKey(defaultName, nil);
    if (v) return [v isKindOfClass:[NSString class]] ? v : [v stringValue];
    return [self rz2099_stringForKey:defaultName];
}
- (BOOL)rz2099_boolForKey:(NSString *)defaultName {
    if (RZKeyEquals(defaultName, @"LicenseAccepted")) return YES;
    return [self rz2099_boolForKey:defaultName];
}
- (NSInteger)rz2099_integerForKey:(NSString *)defaultName {
    if (RZKeyEquals(defaultName, @"LicenseAccepted")) return 1;
    id v = RZForcedObjectForKey(defaultName, nil);
    if (v) return [v integerValue];
    return [self rz2099_integerForKey:defaultName];
}
- (double)rz2099_doubleForKey:(NSString *)defaultName {
    if (RZKeyEquals(defaultName, @"LicenseAccepted")) return 1.0;
    id v = RZForcedObjectForKey(defaultName, nil);
    if (v) return [v doubleValue];
    return [self rz2099_doubleForKey:defaultName];
}
@end

@interface NSDictionary (RazerAuth2099Hook)
@end
@implementation NSDictionary (RazerAuth2099Hook)
- (id)rz2099_objectForKey:(id)aKey { return RZForcedObjectForKey(aKey, [self rz2099_objectForKey:aKey]); }
- (id)rz2099_objectForKeyedSubscript:(id)key { return RZForcedObjectForKey(key, [self rz2099_objectForKeyedSubscript:key]); }
@end

@interface UILabel (RazerAuth2099Hook)
@end
@implementation UILabel (RazerAuth2099Hook)
- (void)rz2099_setText:(NSString *)text { [self rz2099_setText:RZSanitizedText(text)]; }
@end

@interface UIViewController (RazerAuth2099Hook)
@end
@implementation UIViewController (RazerAuth2099Hook)
- (void)rz2099_presentViewController:(UIViewController *)vc animated:(BOOL)flag completion:(void (^)(void))completion {
    if (gRazerAuthHookEnabled && [vc isKindOfClass:[UIAlertController class]]) {
        UIAlertController *alert = (UIAlertController *)vc;
        if (RZLooksLikeAuthAlertText(alert.title) || RZLooksLikeAuthAlertText(alert.message)) {
            if (completion) completion();
            return;
        }
    }
    [self rz2099_presentViewController:vc animated:flag completion:completion];
}
@end

static void RZExchange(Class cls, SEL original, SEL replacement) {
    Method m1 = class_getInstanceMethod(cls, original);
    Method m2 = class_getInstanceMethod(cls, replacement);
    if (m1 && m2) method_exchangeImplementations(m1, m2);
}

static BOOL RZIsSubclassOf(Class cls, Class parent) {
    for (Class c = cls; c; c = class_getSuperclass(c)) {
        if (c == parent) return YES;
    }
    return NO;
}


static BOOL RZClassOwnsInstanceMethod(Class cls, SEL sel) {
    unsigned int count = 0;
    Method *methods = class_copyMethodList(cls, &count);
    BOOL found = NO;
    for (unsigned int i = 0; i < count; i++) {
        if (method_getName(methods[i]) == sel) { found = YES; break; }
    }
    if (methods) free(methods);
    return found;
}

static void RZExchangeWithProvider(Class cls, SEL original, SEL replacement, Class provider) {
    if (!RZClassOwnsInstanceMethod(cls, original)) return;
    Method orig = class_getInstanceMethod(cls, original);
    Method repl = class_getInstanceMethod(provider, replacement);
    if (!orig || !repl) return;
    IMP replImp = method_getImplementation(repl);
    const char *types = method_getTypeEncoding(repl);
    class_addMethod(cls, replacement, replImp, types);
    Method localRepl = class_getInstanceMethod(cls, replacement);
    if (localRepl) method_exchangeImplementations(orig, localRepl);
}

static void RZSwizzleDictionaryClasses(void) {
    int count = objc_getClassList(NULL, 0);
    if (count <= 0) return;
    Class *classes = (Class *)calloc((size_t)count, sizeof(Class));
    if (!classes) return;
    count = objc_getClassList(classes, count);
    Class dict = [NSDictionary class];
    for (int i = 0; i < count; i++) {
        Class cls = classes[i];
        if (RZIsSubclassOf(cls, dict)) {
            RZExchangeWithProvider(cls, @selector(objectForKey:), @selector(rz2099_objectForKey:), dict);
            RZExchangeWithProvider(cls, @selector(objectForKeyedSubscript:), @selector(rz2099_objectForKeyedSubscript:), dict);
        }
    }
    free(classes);
}

__attribute__((constructor)) static void RazerAuth2099Init(void) {
    @autoreleasepool {
        gRazerAuthHookEnabled = RZIsTargetProcess();
        if (!gRazerAuthHookEnabled) return;
        RZExchange([NSUserDefaults class], @selector(objectForKey:), @selector(rz2099_objectForKey:));
        RZExchange([NSUserDefaults class], @selector(stringForKey:), @selector(rz2099_stringForKey:));
        RZExchange([NSUserDefaults class], @selector(boolForKey:), @selector(rz2099_boolForKey:));
        RZExchange([NSUserDefaults class], @selector(integerForKey:), @selector(rz2099_integerForKey:));
        RZExchange([NSUserDefaults class], @selector(doubleForKey:), @selector(rz2099_doubleForKey:));
        RZSwizzleDictionaryClasses();
        RZExchange([UILabel class], @selector(setText:), @selector(rz2099_setText:));
        RZExchange([UIViewController class], @selector(presentViewController:animated:completion:), @selector(rz2099_presentViewController:animated:completion:));
        NSLog(@"[RazerAuth2099Hook] enabled: LicenseAccepted=YES ExpiredText=%@", kRazerFutureText);
    }
}
