/*
 * The MyERP user manual.
 *
 * Every pull request that adds or changes a screen updates its chapter here,
 * so the manual always matches what people see. Write for the person doing
 * the work: short steps, the words on the screen in quotes, no jargon.
 *
 * `pages` lists the screens a chapter belongs to (see `helpTopicFor` in
 * Help.tsx); the Help link in the top menu opens the chapter for the screen
 * the person is on.
 */
import type { ReactNode } from "react";

export type Chapter = { id: string; title: string; summary: string; body: ReactNode };

/** A list of fields: what each one on a form is for. */
function Fields({ rows }: { rows: [string, ReactNode][] }) {
  return (
    <table className="help-fields">
      <tbody>
        {rows.map(([name, what]) => (
          <tr key={name}>
            <th>{name}</th>
            <td>{what}</td>
          </tr>
        ))}
      </tbody>
    </table>
  );
}

function Note({ children }: { children: ReactNode }) {
  return <p className="help-note">{children}</p>;
}

export const MANUAL: Chapter[] = [
  {
    id: "start",
    title: "Getting started",
    summary: "Signing in, finding your way around and saving your work.",
    body: (
      <>
        <h3>Signing in</h3>
        <p>
          Open your company group's MyERP address and click "Sign in with Google". Use the Google account for the email
          address your MyERP admin added for you. If MyERP says your email "does not have access", ask the admin to add you under Users.
        </p>
        <p>To sign out, click "Sign out" at the top right. On a shared computer, always sign out when you finish.</p>

        <h3>The screen</h3>
        <ul>
          <li>
            <strong>Top menu</strong> (white bar): the modules you may use, such as Home, Masters, Users and Roles. You
            only see the ones your role allows. "Help" opens this manual at the page for the screen you are on.
          </li>
          <li>
            <strong>Green band</strong>: where you are (the small links above the title take you back a step), the
            page title, key facts, and the page's main buttons on the right.
          </li>
          <li>
            <strong>Tabs</strong> inside the band split a page into sections, for example a company's Overview,
            Branches, Licences and certificates, and Modules.
          </li>
        </ul>

        <h3>Saving and cancelling</h3>
        <p>
          Every form that adds or changes something has a green "Save" button. "Cancel" closes the form without
          changing anything. If something is missing or wrong, a red message under the form says what to fix, and
          nothing is saved until you fix it.
        </p>

        <h3>Folding lists</h3>
        <p>
          Lists that follow a tree, like ledger groups, have an arrow before each row that has rows under it. Click
          the arrow to fold or unfold. "Show levels" with 1, 2, 3 … All folds the whole list to that depth in one click.
          There is no limit to how deep a tree can go; the buttons match the deepest level in use.
        </p>

        <h3>Home</h3>
        <p>Home lists the companies you work in, with a link to each company and its ledgers.</p>
      </>
    ),
  },
  {
    id: "companies",
    title: "Companies",
    summary: "Adding a company and keeping its registration details up to date.",
    body: (
      <>
        <p>
          A company is one legal entity with its own books, GST registration and document numbers. Open them from
          Masters in the top menu. A new company starts with a Head office branch and the standard ledger groups.
        </p>

        <h3>Add a company</h3>
        <p>Only an Owner can add a company.</p>
        <ol>
          <li>Go to Masters and click "Add company".</li>
          <li>Fill in the details below and tick the modules the company uses.</li>
          <li>Click "Save". The company's page opens.</li>
        </ol>
        <Fields
          rows={[
            ["Legal name", "The name as registered."],
            [
              "Short code",
              "Goes in front of document numbers, for example AOL. Leave it blank to use the initials. It cannot be changed later.",
            ],
            ["GSTIN", "Leave blank if the company is not registered for GST. Typing a GSTIN fills in the PAN and state."],
            ["PAN", "The company's PAN."],
            ["State", "The state of the registered office."],
            ["Type of entity", "Proprietorship, partnership, LLP, private or public limited, or one person company."],
            ["CIN / LLPIN", "Asked for companies and LLPs registered with the MCA."],
            ["Date of incorporation, TAN", "TAN is needed for deducting TDS."],
            ["Registered address and contact", "Address, PIN, phone, email and a contact person."],
            ["Financial year starts in", "Usually April."],
            [
              "Books beginning from",
              "The date your opening balances are as at. Blank means the start of the current financial year.",
            ],
            [
              "Use foreign currencies",
              "Tick for exports, imports or EEFC accounts. Ledgers can then be kept in another currency; the books stay in rupees.",
            ],
          ]}
        />

        <h3>The company page</h3>
        <p>
          Click a company's name. The band shows its GSTIN, PAN and state, and "Ledgers" and "Ledger groups" buttons. The
          Overview tab shows:
        </p>
        <ul>
          <li>
            <strong>Opening balance difference</strong>: debit openings minus credit openings across all ledgers. It
            should be zero once every opening balance is in.
          </li>
          <li>
            <strong>Next renewal</strong>: the licence or certificate that lapses soonest.
          </li>
          <li>
            <strong>Branches</strong>: how many are open.
          </li>
          <li>Registration, address and books details.</li>
        </ul>
        <p>To change the details, click "Edit" in the band, make the changes and click "Save".</p>
      </>
    ),
  },
  {
    id: "branches",
    title: "Branches",
    summary: "Offices, factories and warehouses, and which addresses documents pick first.",
    body: (
      <>
        <p>
          A branch is any place the company works from: head office, factory, warehouse or shop. Every voucher will
          carry a branch, so reports can be seen branch by branch.
        </p>
        <h3>Add or change a branch</h3>
        <ol>
          <li>Open the company and click the "Branches" tab.</li>
          <li>Click "Add branch", or "Edit" on a branch.</li>
          <li>Fill in the details and click "Save".</li>
        </ol>
        <Fields
          rows={[
            ["Name", "For example Bhiwandi warehouse."],
            ["State", "Where the branch is."],
            ["GSTIN", "Only if the branch is registered separately in that state."],
            ["Address and contact", "Address, PIN, phone, email and contact person."],
            [
              "Default addresses",
              "Tick Default billing address, Default ship to or Default ship from. Each can be on only one branch; documents pick it first and you can change it on each document. To move a default, tick it on the other branch.",
            ],
            ["Open", "Untick when a branch closes. The Head office cannot be closed."],
          ]}
        />
      </>
    ),
  },
  {
    id: "certificates",
    title: "Licences and certificates",
    summary: "FSSAI, IEC, Udyam, organic, ISO, LUT and other registrations with renewal dates.",
    body: (
      <>
        <p>
          Keep every registration that has to be renewed here, so the company page can show what lapses next. Types
          include FSSAI, Udyam, IEC, organic (NPOP, NOP, EU), ISO, FSSC 22000, LUT, factory licence, pollution consent,
          shop licence and Other.
        </p>
        <h3>Add a certificate</h3>
        <ol>
          <li>Open the company and click the "Licences and certificates" tab.</li>
          <li>Click "Add certificate".</li>
          <li>
            Choose the type, enter the number, who issued it, the branch (for licences issued per premises, or Whole
            company), valid from and the renewal date. Leave the renewal date blank if it does not lapse.
          </li>
          <li>Click "Save".</li>
        </ol>
        <Note>
          When a certificate is renewed, add the new one as a new certificate. The old one stays on record. Remember
          that the IEC must be updated every year.
        </Note>
      </>
    ),
  },
  {
    id: "modules",
    title: "Modules",
    summary: "Choosing which parts of MyERP a company uses.",
    body: (
      <>
        <p>
          Not every company needs every module; a trading company may not use Production. The "Modules" tab lists each
          module, what it covers, what it needs, and whether this company uses it. Screens for modules that are not used
          stay hidden for that company. Accounts is always on.
        </p>
        <h3>Change the modules</h3>
        <p>Only an Owner can do this.</p>
        <ol>
          <li>Open the company and click the "Modules" tab.</li>
          <li>Click "Choose modules", tick or untick, and click "Save".</li>
        </ol>
        <p>
          Some modules need others: Production and Quality need Stock. Ticking a module also ticks what it needs, and
          unticking Stock also unticks the modules that need it.
        </p>
      </>
    ),
  },
  {
    id: "ledger-groups",
    title: "Ledger groups",
    summary: "The tree that ledgers sit in, following Schedule III.",
    body: (
      <>
        <p>
          Every ledger sits in a group, and groups sit under other groups, as deep as you need. The standard groups come
          with MyERP and follow Schedule III of the Companies Act, so the balance sheet and profit and loss come out in
          the right form. Their familiar names are kept, with the Schedule III head shown beside each.
        </p>
        <p>
          Open them with the "Ledger groups" button on the company page or on the Ledgers screen. The table shows each
          group's nature (asset, liability, income or expense), its Schedule III head and how many ledgers it holds.
          Click a group's ledger count to see those ledgers.
        </p>
        <h3>Add your own group</h3>
        <ol>
          <li>Find the group it belongs under and click "+ Sub-group" on that row.</li>
          <li>Type the name, for example Export debtors under Sundry Debtors, and click "Save".</li>
        </ol>
        <p>The new group takes its nature and Schedule III head from the group above it.</p>
        <h3>Change, move or delete a group you added</h3>
        <p>
          Click "Edit" on its row. You can rename it or choose a different group in "Under". "Delete group" works only
          when nothing is under it: move or delete its sub-groups and ledgers first.
        </p>
        <Note>Standard groups cannot be changed or deleted, because posting rules rely on them.</Note>
      </>
    ),
  },
  {
    id: "ledgers",
    title: "Ledgers",
    summary: "Accounts for parties, banks, expenses and income, with opening balances.",
    body: (
      <>
        <p>
          A ledger is one account: a customer, a supplier, a bank, an expense or an income head. Open Ledgers from Home or
          from the company page. Use the "Ledger groups" button to go back to the groups.
        </p>
        <h3>The screen</h3>
        <ul>
          <li>
            <strong>The list on the left</strong> follows the group tree, with the number of ledgers and the net opening
            balance of each group. Fold groups with the arrows or "Show levels". Type in the search box to find a ledger by
            name or bank account number.
          </li>
          <li>
            <strong>The side panel on the right</strong> shows the ledger you click: its group and nature, opening
            balance (with the foreign currency amount and rate if it has one), currency, whether it is kept bill by bill,
            bank details, opening bills and notes. After clicking a ledger, the ↑ and ↓ keys move through the list. On a
            phone the panel shows above the list.
          </li>
        </ul>
        <h3>Add a ledger</h3>
        <ol>
          <li>Click "Add ledger". The form opens in the side panel.</li>
          <li>Type the name and choose the group it goes under.</li>
          <li>If the company uses foreign currencies, choose the ledger's currency.</li>
          <li>For a bank ledger, fill in the bank, account number, IFSC and branch.</li>
          <li>Enter the opening balance (see below) and click "Save".</li>
        </ol>
        <h3>Opening balances</h3>
        <p>
          The opening balance is the balance on the date the company's books begin. Enter the amount and choose Dr or Cr.
          For a ledger in a foreign currency, enter the amount in that currency and the rate; the rupee amount is worked
          out for you.
        </p>
        <p>
          For customers and suppliers, tick "Maintain balances bill by bill" and enter each unpaid bill with its
          reference, date, due date and amount. The opening balance is then the total of the bills. Bills must be dated
          before the books begin.
        </p>
        <Note>
          Ledgers are never deleted, so past entries always have their account. When a ledger is no longer needed, click
          "Edit" and untick "Active"; it then cannot be used in new entries.
        </Note>
      </>
    ),
  },
  {
    id: "users",
    title: "Users",
    summary: "Letting people sign in and choosing what they can do.",
    body: (
      <>
        <p>
          Only people added here can sign in. They sign in with the Google account for the email you give. You need the
          permission to manage users to see this screen.
        </p>
        <h3>Add a user</h3>
        <ol>
          <li>Click "Users" in the top menu, then "Add user".</li>
          <li>Enter their email (their Google account) and full name.</li>
          <li>Tick their roles. Only an Owner can make someone an Owner.</li>
          <li>Tick the companies they may work in. None ticked means all companies.</li>
          <li>Click "Save".</li>
        </ol>
        <h3>Stop someone signing in</h3>
        <p>Click "Edit" on the user, untick "Active" and click "Save". Their past work stays on record.</p>
      </>
    ),
  },
  {
    id: "roles",
    title: "Roles",
    summary: "Sets of permissions, such as Accountant, Sales or Storekeeper.",
    body: (
      <>
        <p>
          A role is a set of permissions. MyERP comes with standard roles: Owner, Accountant, Sales, Purchase,
          Storekeeper, Production supervisor, Quality and Viewer. A person can have more than one role and gets
          everything each allows.
        </p>
        <p>Owner can do everything and cannot be changed. Only an Owner can change roles.</p>
        <h3>Make or change a role</h3>
        <ol>
          <li>Click "Roles" in the top menu, then "New role", or "Edit" on a role.</li>
          <li>Give it a name and description, tick the permissions in each area, and click "Save".</li>
        </ol>
        <p>Standard roles can be edited but not deleted. Roles you made can be deleted with "Delete role".</p>
      </>
    ),
  },
];
