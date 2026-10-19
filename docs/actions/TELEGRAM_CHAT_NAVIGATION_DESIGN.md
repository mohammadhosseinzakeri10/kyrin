# Telegram chat navigation: first bounded action

## Telegram destination commands (2026-10-18)

With Telegram in the foreground, English commands for Archive, Contacts,
Settings, My Profile, and Calls route through `TELEGRAM_VIEW`. `Create new
group` and `Create new channel` only open their respective creation screens;
they never choose members, enter a name, or submit creation. Existing Telegram
screen and input consent plus a fresh desktop ID/PID match are required.
Archive and Contacts use Telegram Desktop's default Ctrl+9 and Ctrl+J
shortcuts. Other destinations use the main menu: KYRIN locates one exact OCR
label twice before clicking, then checks the destination title. A click with
uncertain title verification is reported as dispatched, not confirmed. The
main-menu geometry and local UI labels require a live owner test on the
installed Telegram build.

The initial live menu test revealed that the top-left button is a back button
inside Archive. Navigation now performs at most two bounded top-left clicks,
checking for a stable menu item after each. A menu target also requires a
second known main-menu label in the same OCR frame, so a similarly named chat
row cannot by itself authorize a click. The rule path accepts `Go to setting`
as Telegram Settings when Telegram is the observed active app.
The owner's STT repeatedly rendered spoken `my calls` as `my carls` in a live
trial. That exact observed spelling is a bounded English alias for Calls while
Telegram is active; unrelated phrases remain unrecognized.

## Status and evidence

The Ubuntu application has a verified `Saved Messages` action and a guarded
search path for other Telegram chat names.
`OPEN_CHAT` is enabled only when Telegram is allowed, a separate Telegram chat
permission is saved, the active-app observer is present, and the Qt screen
verifier and focused-window identity reader are supplied. Opening an arbitrary
chat has not yet been confirmed in a live product-path test. The initial
settings grant no chat permission.

The session-scoped GNOME capture path identified the real Telegram Desktop
window by desktop ID and PID. English OCR found several known Settings labels
and one visible `Saved Messages` title in controlled read-only tests. Those
tests did not select a row. The installed OCR data is English only. Telegram
has not yielded a dependable AT-SPI tree in earlier repository diagnostics.

`kyrin.vision.text_targets.find_exact_phrases` now returns all adjacent,
same-line exact OCR matches and their image boxes. It deliberately keeps
duplicates and does not authorize a click. The box is relative to the captured
image, not a verified desktop action coordinate.

## First vertical slice

Start with Telegram's built-in Saved Messages action. The Telegram Desktop
source lists a `ChatSelf` keyboard command and a default `Ctrl+0` binding on
non-Mac platforms. Verify that binding on the installed version before using
it; users can customize shortcuts. This slice needs keyboard permission only,
not pointer permission or OCR-derived coordinates. After invoking it, KYRIN
must capture a fresh Telegram window and verify the expected chat title.
No message text is typed and no message is sent. The installed Telegram
shortcut file maps `self_chat` to `Ctrl+0`; its custom shortcut file contained
no override. In one owner-approved live diagnostic, the non-persistent portal
granted keyboard access, the fixed shortcut was dispatched only after matching
Telegram's desktop ID and PID, and the portal session was closed. A subsequent
read-only capture found `Saved Messages`, and the owner independently confirmed
the chat opened. The first OCR result alone did not prove that the title was in
the opened-chat header. A later read-only capture found one `Saved Messages`
phrase in the upper chat pane at x=679, y=45 in a 1853×1048 image. The product
verifier now requires a fresh matching desktop ID/PID and one sufficiently
confident phrase in that pane. This may reject changed Telegram layouts.

The application requests keyboard access only after checking screen
access and Telegram focus. The helper rechecks desktop ID and PID before
dispatching `Ctrl+0`, closes the portal session, and the Qt-owned OCR reader
verifies the result. Uncertain verification never reports completion. This
combined application path has deterministic tests and one successful
end-to-end live microphone check on the owner's current Ubuntu desktop.

The first product-path microphone trial recognized `open_chat` and the
foreground Telegram app, but Whisper returned `Saved Massages` for the spoken
`Saved Messages`. The executor rejected that target as `unsupported_chat`
before requesting keyboard access. The observed exact spelling is now an
additional, narrowly scoped alias for the same built-in Telegram action.
All existing permission, foreground identity, and fresh OCR header checks
still apply. After restarting KYRIN, the owner repeated the complete command.
The interpreter again produced `open_chat: saved massages`, the action result
was `confirmed`, and the owner reported that the chat opened. The first two
short fragments in that run produced no action. The reported final-text-to-
result interval was 16,849 ms; this single run includes the temporary input
permission and OCR path and does not isolate their individual costs.

In a later owner test, STT produced `open_chat: save the messages` for the
same intended chat. That target followed the generic Telegram search path,
which typed the phrase into search but stopped with `chat_search_uncertain`
before clicking any result. The exact observed phrase now resolves to the
Saved Messages shortcut, with the existing permission, focused-window, and
fresh header verification checks. After restarting KYRIN, the owner reported
that the chat opened. The microphone diagnostic showed
`open_chat: save the messages` and `Action result: confirmed`, with 1,500 ms
from final transcript to result in that run. This validates the reported
variant in the owner's session; it is not a general chat-name recognition
result.

For a repeatable product-path check, start listening in the installed KYRIN
control center, enable remembered screen access, and keep Telegram in the
foreground. Say `Open chat Saved Messages` once. Record the final `Heard`,
`Interpreted command`, and `Action result` or clarification in Speech
Recognition diagnostics, and confirm visually whether the chat opened. No
message should be typed or sent in this check.

The next bounded `OPEN_CHAT` slice for other names uses a Telegram search
shortcut and types at most 64 permitted characters without Enter. A fresh
OCR read must find one exact target in the left results pane below search;
a second read must return the same box and window identity. Only then does a
separate pointer portal grant allows a click. The helper compares
the focused Telegram desktop ID/PID, the window frame to the OCR image size,
and the resulting cursor position before pressing the left button. A fresh
OCR read must then confirm the exact target in the upper chat header. No text
is sent as a message. If a match is absent or ambiguous, the search layout is
uncertain, the pointer grant is denied, or focus changes, the action stops.
The owner approved the new pointer scope with system consent. This slice has
deterministic tests and awaits extension reload and live validation; it does
not claim general multilingual chat navigation, because installed OCR data is
currently English-only.

## Ubuntu input boundary

This GNOME session is Wayland; `xdotool`, `ydotool`, and `wtype` are not
installed. The local XDG Desktop Portal exposes `RemoteDesktop` version 2
with keyboard and pointer devices. Desktop Actions has a setup button that
requests both devices together with `persist_mode=2` and saves an opaque
restore token with mode 0600. Each successful `Start` rotates that single-use
token. If the saved setting or token is missing, chat actions stop before an
action-time system consent request. The OS may still show a dialog if it
revokes or cannot restore a saved grant. Disabling Telegram chats or the
remembered grant deletes KYRIN's local token. Each action still gets a
short-lived session that is closed afterward. The portal controls desktop
input, not one named window;
KYRIN must check the Telegram desktop ID and PID before each short input
sequence and verify the result afterwards. A focus change between a check and
an input event remains a residual risk. The owner accepted this permission
scope for a one-shot diagnostic. The same helper now lives in
`src/kyrin/actions/platforms/telegram_portal_helper.py`. The app settings and
action gate apply a separate chat allowlist before it can run. The portal
dialog grants desktop input access for that temporary session. The
helper polls for the exact Telegram desktop ID and PID for up to ten seconds
after the dialog, requires two matching observations 150 ms apart, then sends
only the fixed shortcut. It no longer waits for all ten seconds when Telegram
is already in the foreground. The identity check cannot eliminate a focus
change between the final observation and the keyboard event. General chat
navigation remains unavailable.

In one owner-confirmed repeat of the complete spoken command after this
change, KYRIN heard `Open Chat Saved Messages`, opened the chat, and reported
`confirmed`. Final-text-to-result time was 6,187 ms, compared with 16,849 ms
in the earlier run with the fixed sleep. The difference is consistent with
removing the unconditional wait, but these two runs do not isolate permission
dialog or OCR timing.

Keep this permission-aware input adapter separate from `OcrEngine`,
`ScreenTextReader`, `ActionGate`, and the Telegram-specific navigation logic.
Other operating systems can supply their own adapters without changing the
command contract. The action gate still requires an explicit allowed chat app.

## Case handling and first named-chat baseline

OCR phrase matching uses Unicode normalization and `casefold()` on both the
requested chat title and recognized words; it does not enumerate capitalized
spellings. A live `Open Chat My Mother` trial on 2026-10-16 reached
`open_chat: my mother` and stopped with `chat_search_uncertain` after typing
the lower-case target. A read-only selected-window OCR check found one
high-confidence phrase match at the top search field (x=67, y=45), not
in the result list. The owner then reported that manually entering the exact
visible spelling `My Mother` made the chat result appear. This points to lost
source capitalization before Telegram search, not an OCR case-comparison
failure. No result was clicked in the failed run.

The interpreter now compares commands case-insensitively while preserving the
chat name's original spelling from the final transcript for external search.
The same recovery applies to model-resolved chat names only after source
grounding accepts them. After restart, a repeat live microphone check produced
`open_chat: My Mother` and typed the exact spelling. The owner's own chat row
was visible but the action still stopped at `chat_search_uncertain`. A
read-only OCR capture found the search input at y=45, the local chat row at
y=92, and four same-name matches lower in Global Search Results. The old
verifier's vertical filter missed the local row and treated the repeated lower
matches as ambiguous.

The owner requested a two-stage clarification when both kinds of result are
visible: first choose the local chat or Global Search Results, then choose a
numbered global row if needed. The OCR parser separates these candidates and
exposes them through the Qt screen verifier. The live command runtime now
intercepts a final spoken answer while the selection is pending. The response
announces the local/global choice, then numbers the matching global rows from
top to bottom. Invalid answers repeat the question; cancellation or expiry
discards the choice. Before clicking, the action reads Telegram again and
requires the same focused window identity, number of rows, image size, and
boxes within a 5-pixel tolerance. The helper then checks focus and pointer
position, and a final OCR read checks the opened chat header.

The current parser records only exact-name OCR matches in the lower list; it
does not yet enumerate every visible global result or its display label. A
live named-chat opening after this dialogue change has not been confirmed.
Two subsequent owner runs still stopped before prompting. Their choice-read
statuses were `unclassified_matches_1` and `classified_own_0_global_0`.
The settle loop now waits through empty classifications instead of accepting
them as stable results. The next live diagnostic records only image dimensions
and target-match positions, allowing a layout or OCR miss to be distinguished
without retaining a screenshot or message content.
An owner-authorized read-only capture of a later KYRIN search showed the
target only inside the search field, while the owner reported that manual
re-entry produced the chat row. Because `Ctrl+F` can search within the open
conversation, the keyboard helper now presses `Esc` before focusing search,
then selects existing search text before typing the target. This suspected
search-scope cause requires live validation. The pointer geometry guard also
now admits the observed local row at y=92/1080 while still rejecting the
search field at y=45/1080. Focused tests cover both positions.
The owner subsequently confirmed the key context difference: with a chat
open, the prior shortcut searched within that chat; with the chat closed, the
result list appeared. The search helper now sends two `Esc` keys before
`Ctrl+F`, checks that Telegram remains focused, and replaces any old query.
The in-app OCR once found four title locations but rejected classification;
the parser now accepts a lower-confidence query-field title while retaining
the stronger threshold for clickable result rows. This combination still
needs a live open-chat retest.
In that retest, search results appeared but no choice prompt did. The in-app
query title had only 5% OCR confidence while the local row and one global row
each had 96%. The query confidence floor was therefore removed: the query
must still match exactly and uniquely in the search-field geometry, and
result rows retain the 75% threshold and stable reread requirements. The
choice prompt after this correction has not yet been observed live.
In the next retest, OCR missed the query altogether but found the local row
and one global row at 96% confidence. Classification now permits a missing
query for a choice prompt only when the unique local row is found in the
expected left-pane band. Automatic single-result clicking still requires an
exact query-field match. Fresh stable reads and the final pointer and header
checks remain in place. This adjustment awaits live validation.

The owner subsequently confirmed that `My Mother` opened with `Action result:
confirmed` from an initially open chat. The current desired behavior is to
open one matching existing chat directly and ask for a number only when
multiple existing chats share the name. `Search Results` separates local
chat rows above it from global results below it when OCR recognizes the
section title. Local rows take priority: lower global matches do not trigger
a question when there is exactly one local match. Multiple local rows are
numbered top to bottom, with a fresh stable reread before clicking. Global
results alone do not start this selection flow. This duplicate-name path has
only deterministic coverage so far; the owner has not tested it with two
real same-name chats.

The first selection implementation emitted its question while the visual
controller still marked the action as executing. The controller consequently
kept the `Opening ... chat` caption and ignored the question. The selection
prompt now explicitly switches the visual state to `QUESTION`; an unanswered
selection expires after 45 seconds and publishes failure feedback. Quit and
session shutdown cancel a pending selection. Live validation of this fix
is pending.

In the next owner trial, the question appeared, but answering `One` or
`Number 1` failed during the fresh read before clicking. The stable-choice
comparison previously included all global rows, though only local rows could
be selected. It now compares local rows only; changing global results cannot
invalidate the chosen local row. Failure feedback distinguishes a missing
fresh read from changed local rows. In a subsequent owner run, answering
`Number One` reached the system pointer-permission dialog. The selected chat's
final open result is still unconfirmed.

## Advance Telegram control setup

The owner observed a system pointer-consent dialog on every named-chat click.
The first implementation remembered pointer access but requested consent at
the first click. Desktop Actions now has a setup button for one combined
keyboard-and-pointer `RemoteDesktop` grant. The owner saves the chat/control
setting and presses that button before issuing a chat command. Successful
setup stores the new `telegram-control` restore token; each action submits it
and saves the replacement. Without this token, the action reports a setup
requirement before opening a portal session. Unchecking the setting or
disabling Telegram chats removes the token. The system can still ask again
if it revokes permission or cannot restore the saved grant.
KYRIN still checks Telegram focus, OCR box geometry, pointer position, and
the final chat header for each action.
The owner subsequently reported that the in-app setup and numbered chat
selection worked in a live run without the previous permission interruption.

## Duplicate local rows and global-only results

In a later live test with two local chats called `My Mother`, `Number 2`
incorrectly opened the first chat. Read-only OCR geometry revealed a repeated
name in the first row's preview at x=350, y=116, between the real chat titles
at y=92 and y=154. The local-row classifier now confines titles to the left
title column. It can recognize the global section when OCR retains only the
word `results`, and can retain adjacent local rows when that heading is missed.
The same live search image now classifies local rows `(92, 154)` and global
rows `(244, 306, 430, 554)`. The owner restarted KYRIN and reported that
`Number Two` opened the intended second chat.

If there is no local match, KYRIN now asks for a number from the global
results only when the global section heading is visibly recognized. It
rechecks the numbered global rows before clicking and stops if they move.
One local match still opens directly; multiple local matches remain a
local-only choice. The global-only path has deterministic coverage but awaits
a live test with a suitable search name.

### Spoken choice forms

The same pending-choice parser handles local and verified global results.
Replies can be digits (`2`), cardinal numbers (`two`, `number two`), or
ordinals (`second`, `the second`, `the second one`, `2nd`). It also accepts
`option two`, `option number two`, `second option`, and explicit selection
phrases such as `choose the second` or `select option 2`. English number and
ordinal words cover one through ten; numeric replies are checked against the
actual number of choices. Standard Persian numbers and ordinals are supported
by the parser as well. Letter case and surrounding whitespace do not matter.

This is an exact whole-answer grammar: `one or two`, `not the second`, and an
unavailable number do not select a row. The question is repeated, and all
successful answers still pass the fresh visual checks before a click. New
reply forms are covered by deterministic tests; microphone recognition is a
separate live check. Use clearly pronounced English names for the current
navigation test; custom-name STT accuracy remains a separate work item.

### Search scope and alternate English phrasing

The single-command interpreter now accepts both `Open chat My Mother` and
`Open My Mother chat` (including `Open My Mother's chat`). Source grounding
for model-proposed commands recognizes the same suffix form and still checks
the spoken chat name before any action. The command preserves the final
transcript's spelling for Telegram's search field; this does not repair a
name that STT transcribed as a different word.

Named-chat navigation searches through Telegram's own search field after
leaving an open conversation. It does not inspect or scroll the initial chat
list, so a chat's position below the initial viewport is not a prerequisite
for the command. The OCR verifier examines currently visible result rows.
The archived chat has not been verified by a supplied action diagnostic. In
the owner's Telegram, searching `My Mother` after archiving one of two
same-name chats showed the ordinary row first and the archived row second,
both above `Global Search Results`. This demonstrates that the current search
surface exposes that archived chat without entering Archive. The first KYRIN
run after archiving ended with `chat_selection_cancelled`; selecting the
archived row was then selected in a separate owner run with `Number Two`; the
owner confirmed that the archived chat opened. No final diagnostic line was
supplied for that run.

In a live owner test, `Open my mother chat` produced `open_chat: my mother`,
asked for a numbered match, and completed with `Action result: confirmed`
after `First`. The owner confirmed the selected chat was an ordinary chat.

## Bounded desktop and Telegram result scrolling

KYRIN now has a separate, default-off Desktop Actions switch for scrolling in
selected apps. The owner saves that setting and sets up a remembered pointer
grant before a spoken `Scroll down` or `Scroll up` action. The command applies
to the currently focused selected app and aims near the center of its window
(the left chat list in Telegram). It sends twelve small touchpad-style axis
events across about 440 ms, checking focus during the sequence. Desktop ID,
PID, window geometry, and pointer position are checked before dispatch. The
portal grant is separate from
Telegram's chat-control token and can be revoked by turning off the scroll
setting. `LAUNCH_ACCEPTED` means the scroll event was dispatched while focus
remained matched; it does not prove content moved.

`Down`/`Up` and `Come down`/`Come up` are short forms. `More` repeats the
direction and amount of the last scroll within 30 seconds while the same app
is active. An explicit `Scroll down more` or `Scroll up more` sends four units;
`Scroll down less` or `Scroll up less` sends two units. Plain `Scroll down/up`
keeps the owner-approved default of three units. The observed ASR wording
`More Scrolls Down` is accepted as an ordinary down command. Each unit maps
to four small smooth-axis events; the total input remains bounded.
The owner microphone retest confirmed `More` after up and `Scroll down more`.
STT rendered other tries as `More Skool Up`, `Scroll down list`, and
`Scroll up Liz`; these exact scroll-shaped spellings are accepted. A lone
`Oh` remains non-actionable because it is ambiguous ordinary speech.

Telegram voice scrolling now supports an explicit area. `Scroll chat down`
or `Scroll up in the chat` aims the smooth pointer-axis input inside the open
conversation at 65% of the window width; `Scroll chat list down` targets the
left chat list at 15%. `More` repeats both the previous direction and area.
The short `Scroll down/up` command keeps its existing left-list target.
Other applications continue to use the window center. These commands reuse
the saved general desktop-scroll grant, with the same fresh app/PID and pointer
checks. Deterministic tests pass; movement inside a live Telegram conversation
was subsequently confirmed by the owner. No action diagnostic was supplied.

Telegram named-chat search can now scroll the left results pane up to four
times, with a total scan deadline, when no selectable exact-name result is
visible after typing the target. Each move is followed by fresh OCR and
stable-row checks. A pending numbered selection also accepts `next`,
`next page`, `more results`, or Persian `بعدی` to show another visible page,
up to page five. The current page is reread before scrolling; the next page
must have a changed in-memory digest of visible left-pane OCR text. That
digest is not logged or persisted. Selecting a number still rechecks the
focused Telegram window and current result boxes before clicking.

When one personal chat is visible but the Global Search Results boundary is
not verified, that row is no longer treated as unique. KYRIN asks for a
number and offers `next` so an offscreen same-name chat can be reached. A
visible, verified global boundary still permits automatic opening of one
personal match. Numbered result paging preserves the personal/global category;
it refuses to switch a personal choice to global rows, and retains the global
category after its heading has scrolled away. A later personal-chat page is
offered only when its local rows appear above a verified section boundary;
an ambiguous page stops safely. A numbered click followed by a
matching chat header reports `launch_accepted`, because equal chat titles
cannot prove which account or conversation was opened. The user-facing reply
states this limitation. Bounded paging and these safeguards have deterministic
tests; offscreen duplicate and global-only pages still need live owner tests.
Spoken `Cancel` is also recognized while a page read or numbered click is in
progress. Cancellation prevents a click that has not yet started. If Telegram
already received a click, KYRIN reports that actual result instead of silently
hiding it; an in-flight OS input cannot be undone.

In the first owner microphone test, `Scroll down` reached the portal and
returned `confirmed` but the Telegram page did not visibly move. That exposed
the center-of-window aim and the overstrong result label; both were corrected.
The first action showed the Remote Desktop dialog, while the next two actions
did not. The owner then confirmed the corrected aim moves the Telegram chat
list on four consecutive commands; no new portal prompt was reported. The
owner found the three-detent movement too abrupt, so the general scroll input
was changed to a bounded smooth axis series. In the next live retest the owner
confirmed that it moved the list smoothly twice with `launch_accepted`, but
requested slightly slower movement; the interval was increased from 25 to
40 ms and needs a final live feel check. The observed phrase
`More, Scroll Down` is now accepted. The Telegram
result paging route has deterministic tests but no live validation yet.
Results beyond the four automatic scrolls or five spoken
pages remain outside the current bound. Duplicate same-name rows split across
pages are numbered per visible page.

References: [XDG RemoteDesktop portal](https://flatpak.github.io/xdg-desktop-portal/docs/doc-org.freedesktop.portal.RemoteDesktop.html),
[Telegram Desktop shortcut source](https://github.com/telegramdesktop/tdesktop/blob/dev/Telegram/SourceFiles/core/shortcuts.cpp).

## Telegram Settings navigation (2026-10-18)

The English voice grammar now recognizes the owner's named Settings sections,
plus `Go to Back` and `Cancel`, only when Telegram is the freshly observed
foreground app. Each section is an exact, case-insensitive spoken label mapped
to a visible label. It does not synthesize arbitrary Telegram actions.

Section navigation reads the active Telegram window through OCR. A settings
row is eligible only when a unique Settings heading appears above it in the
right pane, its text is unique and high confidence, and two reads agree on
its position. The RemoteDesktop helper separately checks the Telegram app/PID,
unchanged window geometry and pointer position before clicking. If the row
is not visible, the executor can open Settings through the existing verified
menu path and scan up to three right-pane scrolls. It stops without a settings
click on uncertain or missing labels. The destination title must be observed
to report `confirmed`; otherwise the result is `launch_accepted`.

`Back` and `Cancel` currently send one Escape to the focused Telegram window
and report only dispatch. Escape may close a menu or dialog rather than return
to the prior settings page; the resulting page is not yet verified. `Cancel`
for a pending chat or app clarification retains its earlier dialogue behavior.

The section labels were supplied by the owner. A screenshot of Telegram
Desktop 7.3.1 now confirms the visible top-level rows described below.
Individual switches, colors, account settings,
and sensitive changes are **not yet implemented**. The agreed rule for future
sensitive changes is a separate voice confirmation before committing them.
Implementation of each control requires a verified current-state reader and
post-change observation; OCR of a label alone is not enough to infer a toggle
state. Nested control changes still need their own observed UI states to
ground a safe implementation.

The owner's later STT output rendered `Go to setting` as `go to seating` and
the generic app resolver asked whether to open the Settings application.
The exact observed `seating` and `my seating` phrases now map to Telegram
Settings only when Telegram is the freshly observed foreground app. The
direct rule also supersedes an older pending app-name clarification. The
application Settings command remains separate outside that context.

In a later live trial, `go to seating` reached `telegram_view: settings`, but
the top-left menu opened without entering Settings. The action spent about
14 seconds after the final transcript and returned `telegram_menu_uncertain`.
The owner's screenshot of the open menu was read with the installed OCR
runtime. Whole-window OCR found no menu words; OCR of the left 30% and top
65% of the same pixels found the Settings label at `(61, 432)` with 0.77
confidence, plus the other menu labels. Menu verification now requests that
cropped region, while preserving original full-window dimensions for the
subsequent geometry and pointer checks. The pre-menu OCR check stops after
one missing read and post-menu matching uses at most three. The destination
Settings title is checked in the right pane. The cropped read and menu
matcher passed on the supplied screenshot; the complete live command awaits
owner retest.

The owner later confirmed Settings opens, but `Go to My Account` returned
`telegram_setting_not_found` after about 32 seconds and the executor tried to
open Settings again. The supplied Settings screenshot shows `My Account` as the
first row in a centered panel. The installed Tesseract runtime recognized both
`Settings` and `My Account` in that screenshot; replacing OCR is not supported
by this evidence. Settings-item and Settings-title verification now OCR only
the centered panel and translate text boxes back to full-window coordinates.
When the Settings title is already visible, a missed row no longer reopens the
main menu. `My Account` is the fixed first row, so a miss does not trigger
useless scrolling. A live owner retest is still needed to verify the corrected
desktop behavior.

The screenshot confirms these top-level rows: My Account, Notifications and
Sounds, Privacy and Security, Chat Settings, Folders, Advanced, Speakers and
Camera, Battery and Animations, Language, Telegram FAQ, Telegram Features, and
Ask a Question. `Default interface scale` is a control, not a destination;
`Go to` does not click it. The earlier `Default`, `Interface`, and `Skills`
destinations did not appear as separate rows in this screenshot and were
removed from the fixed list. Known spoken names remain short aliases. For an
unlisted visible row, `Open settings <label>` or
`Go to <label> in Telegram settings` sends the exact spoken label to OCR
verification. It can click only one stable matching row below the Settings
title; it does not infer, toggle, or commit a settings value. This keeps new
navigation labels data-driven without granting arbitrary screen clicks.

For shorter speech, a successful *interpretation* of `Go to Settings` gives
the next 90 seconds of Telegram dialogue a Settings-navigation context.
During that period, `Go to <label>` can name an unlisted row. The executor
must freshly verify that the Settings title is visible before looking for or
clicking that row. This context is only a routing hint; it does not establish
that the UI action succeeded, and it is cleared by Back/Cancel or another app
command. Known forms such as `Go to My Account` continue to work directly.

In a later live trial, the owner said `Go to Chat Setting` but STT produced
`go to chat seating`. That exact observed variant now maps to Chat Settings,
including after `Cancel` clears the dialogue context. The owner also supplied
an Advanced-page screenshot and confirmed `Back` moves one Settings level up.
The OCR reader now makes a narrower center-panel read for the current page
header. If a known top-level section is requested while a nested page such
as Advanced is open, the executor sends a bounded Back input, verifies that
the root Settings heading reappears, and then searches for the requested row.
It stops if the return cannot be verified. The supplied root and Advanced
screenshots both yielded the expected headings with the installed OCR runtime.
The new voice flow still needs live validation.

Arbitrary controls within Advanced are not yet actionable through this path.
OCR text can locate a label but cannot by itself establish whether the row is
a navigation target, a checkbox, a switch, or a value with side effects. A
cross-app screen-navigation layer should combine a fresh foreground-window
identity, UI roles when available, OCR for visible text, and post-action state
checks. It should capture only on a relevant command and read the smallest
useful region to keep latency bounded. This broader layer remains a proposal.

## Explicit Telegram search (2026-10-18)

`Go to search` and `Open Telegram search` focus Telegram's global search box.
`Search for <name>`, `Search Telegram for <name>` and
`Find <name> in Telegram` type a bounded name and leave the results visible;
they do not press Enter or select a result. These commands require freshly
observed Telegram focus and the saved control permission. The helper exits an
open conversation before Ctrl+F, matching the existing named-chat search
behavior. A typed query is reported as confirmed only if OCR sees its exact
case-insensitive text in the left search field; otherwise the result merely
says input was dispatched. Automatic result selection remains the separate
`Open chat <name>` flow. This path has deterministic tests but no owner live
validation yet.
