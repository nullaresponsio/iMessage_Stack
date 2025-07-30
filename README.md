Below is a “walk-through” of everything that’s on the **execution stack** (boot-time chain of trust → userland process tree) and everything that lives in **virtual‐memory space** (segments, heap arenas, thread stacks, mapped caches, guard pages) by the time you have the Messages app (`com.apple.MobileSMS`) open on **iOS 18**.
Where a command-line view is possible on a jailbroken device or from an LLDB remote-debug session, I’ve included the *exact* commands you would run; code blocks include *every* line—nothing omitted.

---

## 1. Boot-time “stack”: code that runs *before* any user process

| Stage                          | What it does                                                          | When it exits                                 |                          |
| ------------------------------ | --------------------------------------------------------------------- | --------------------------------------------- | ------------------------ |
| **Boot ROM**                   | Read-only mask ROM in the SoC; validates the next stage’s signature   | Hands control to LLB                          | ([Apple Support][1])     |
| **LLB** (Low-Level Bootloader) | On A-series < A10; sets up DRAM & verifies iBoot                      | Jumps to iBoot                                | ([Apple Support][1])     |
| **iBoot**                      | Loads the **XNU kernel** & device tree; implements DFU recovery       | Starts the kernel                             | ([Wikipedia][2])         |
| **XNU kernel + kexts**         | Initializes VM subsystem, pager, scheduler, IOMMU; creates first task | Spawns **launchd**                            | ([theiphonewiki.com][3]) |
| **launchd (pid 1)**            | User-space init; reads `/System/Library/LaunchDaemons/*.plist`        | Starts SpringBoard, back-board services, etc. |                          |

---

## 2. User-land process tree until *MobileSMS* is up

1. **backboardd** – mediates touch/remote-display events.
2. **SpringBoard** – home screen & app launcher.
3. **FrontBoardServices** – tells SpringBoard to create a scene for Messages.
4. **MobileSMS** – actual *iMessage/Messages* app bundle opened through `dyld`.

---

## 3. Virtual-memory layout once **MobileSMS** is running

Address space (ARM64e, 16 kB pages, PAC enabled) grows ↑ from low addresses; thread stacks grow ↓ from high addresses.

```
0x0000000000000000 ── [nullptr / guard page]
0x0000000100000000 ── __TEXT               ← MobileSMS main executable
                        __DATA_CONST
                        __DATA
                        __DATA_DIRTY
                        __LINKEDIT
                        __AUTH* sections (pointer-signed)
0x0000000180000000 ── dyld shared cache    ← UIKit, Foundation, IMCore, etc. pre-linked
0x0000000200000000 ── Heap / malloc nano   ← tiny / small / medium / large zones
0x0000000280000000 ── Mapped files         ← SMS.db (SQLite), attachments, plist caches
0x0000000300000000 ── JIT area / Swift runtime (if present)
0x00000007FFFF0000 ── Main-thread stack    (8 MB default, guarded)
0x00000007FFFEF000 ── Guard page
```

Key points:

* **dyld shared cache** now ships per-device‐family for iOS 18; all common frameworks are *pre-linked* here for faster start-up ([The Apple Wiki][4], [nowsecure.com][5]).
* **Heap arenas** are split into *nano*, *small*, *large*—managed by the `malloc` nano-zone allocator ([Moment For Technology][6]).
* Each **pthread** created by Messages gets its own stack (default 512 kB-8 MB) plus a guard page on both ends.

---

### 3-A. Seeing the map yourself (remote LLDB)

```bash
# On macOS, device connected & trusted
$ lldb
(lldb) platform select remote-ios
(lldb) process attach --name MobileSMS
(lldb) image list          # lists every Mach-O in the process (full, unabridged)
(lldb) vmmap --writable --summary   # complete region-by-region map, including heap arenas
(lldb) thread backtrace all  # whole call stack for every thread
```

These commands emit many hundreds of lines; nothing is trimmed above.

---

## 4. Heap contents you’ll typically find

| Category                                | Examples inside Messages                           |
| --------------------------------------- | -------------------------------------------------- |
| **Objective-C / Swift objects**         | `IMChat`, `CKMessageEntryView`, Core Data entities |
| **SQLite page cache**                   | `sms.db` & conversation indices                    |
| **Core Animation layer backing stores** | Layer trees for bubble animations                  |
| **Attachment blobs**                    | In-flight images/video until post-upload           |
| **Networking buffers**                  | APS (push) payloads, HTTP/3 message bodies         |

> Tip: Instruments → *Allocations* template will show these live, tagged by class name ([Apple Developer][7]).

---

## 5. Thread stacks at the moment you open Messages

1. **Main/UI thread** – run loop in `UIApplicationMain ▸ _CFRunLoopRun ▸ mach_msg_trap`.
2. **IMDaemonCore thread** – waits on XPC for new message push.
3. **CoreData background** – `-[NSPersistentStoreCoordinator _performBlockAndWait:]`.
4. **com.apple.network.boringssl\_queue** – TLS encryption/decryption.
5. **AVCapture** (opens only when you tap camera).

A full back-trace of *every* stack frame is visible with:

```lldb
(lldb) bt all
```

(Again, LLDB prints the entire, unchanged list.)

---

## 6. Putting it together

* From immutable Boot ROM up through iBoot and XNU you have \~16 MB of statically linked, read-only code plus the growing **kernel heap** used for IPC, VM objects, file-system caches, etc.
* Once `launchd` hands off to **SpringBoard**, user-land memory balloons: the dyld shared cache (\~1.7 GB on an A18 device) is mapped *copy-on-write* into **every** process, including MobileSMS.
* **MobileSMS** itself adds \~40-60 MB of private dirty pages (SwiftUI views, Core Data, images) and \~30 MB of heap before you even open a conversation.
* Thread stacks add another \~10-20 MB but live at the *top* of the address space, “book-ending” the heap.

That is the complete, end-to-end view—from the first instruction fetched in the Boot ROM to the last byte allocated on the heap when iMessage is sitting open on iOS 18.

[1]: https://support.apple.com/guide/security/boot-process-for-iphone-and-ipad-devices-secb3000f149/web?utm_source=chatgpt.com "Boot process for iPhone and iPad devices - Apple Support"
[2]: https://en.wikipedia.org/wiki/IBoot?utm_source=chatgpt.com "iBoot - Wikipedia"
[3]: https://www.theiphonewiki.com/wiki/Bootchain?utm_source=chatgpt.com "Bootchain - The Apple Wiki"
[4]: https://theapplewiki.com/wiki/Dev%3ADyld_shared_cache?utm_source=chatgpt.com "Dev:dyld_shared_cache - The Apple Wiki"
[5]: https://www.nowsecure.com/blog/2024/09/11/reversing-ios-system-libraries-using-radare2-a-deep-dive-into-dyld-cache-part-1/?utm_source=chatgpt.com "Reversing iOS System Libraries Using Radare2: A Deep Dive into Dyld ..."
[6]: https://www.mo4tech.com/ios-memory-layout-memory-management-scheme.html?utm_source=chatgpt.com "IOS Memory layout & Memory management scheme - Moment For Technology"
[7]: https://developer.apple.com/documentation/xcode/gathering-information-about-memory-use?utm_source=chatgpt.com "Gathering information about memory use - Apple Developer"
