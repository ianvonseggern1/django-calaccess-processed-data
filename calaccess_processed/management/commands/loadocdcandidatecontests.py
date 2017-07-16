#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
Load CandidateContest and related models with data scraped from the CAL-ACCESS website.
"""
from django.db.models import Case, When, Q, Value
from django.db.models.functions import Cast, Concat
from django.db.models import IntegerField, CharField
from calaccess_processed.models import Form501Filing
from opencivicdata.core.models import Membership, Organization
from opencivicdata.elections.models import CandidateContest, Candidacy
from calaccess_processed.management.commands import LoadOCDModelsCommand
from calaccess_processed.models.proxies import ScrapedCandidateElectionProxy


class Command(LoadOCDModelsCommand):
    """
    Load CandidateContest and related models with data scraped from the CAL-ACCESS website.
    """
    help = 'Load CandidateContest and related models with data scraped from the CAL-ACCESS website.'

    def add_arguments(self, parser):
        """
        Adds custom arguments specific to this command.
        """
        parser.add_argument(
            "--flush",
            action="store_true",
            dest="flush",
            default=False,
            help="Flush the database tables filled by this command."
        )

    def handle(self, *args, **options):
        """
        Make it happen.
        """
        super(Command, self).handle(*args, **options)
        self.header("Load Candidate Contests")

        # Flush, if the options has been passed
        if options['flush']:
            self.flush()

        # Load everything we can from the scrape
        self.load()

        # connect runoffs to their previously undecided contests
        if self.verbosity > 2:
            self.log(' Linking runoffs to previous contests')
        runoff_contests_q = CandidateContest.objects.filter(
            name__contains='RUNOFF'
        )
        for runoff in runoff_contests_q.all():
            previous_contest = self.find_previous_undecided_contest(runoff)
            if previous_contest:
                runoff.runoff_for_contest = previous_contest
                runoff.save()

        self.success("Done!")

    def flush(self):
        """
        Flush the database tables filled by this command.
        """
        models = [Candidacy, CandidateContest]
        for m in models:
            qs = m.objects.all()
            if self.verbosity > 0:
                self.log("Flushing {} {} objects".format(qs.count(), m.__name__))
            qs.delete()

    def load(self):
        """
        Load OCD Election, CandidateContest and related models with data scraped from CAL-ACCESS website.
        """
        # See if we should bother checking incumbent status
        members_are_loaded = Membership.objects.exists()

        # Loop over scraped_elections
        for scraped_election in ScrapedCandidateElectionProxy.objects.all():

            # Get election record
            ocd_election = scraped_election.get_ocd_election()

            # then over candidates in the scraped_election
            for scraped_candidate in scraped_election.candidates.all():
                if self.verbosity > 2:
                    self.log(
                        ' Processing scraped Candidate.id {} ({})'.format(
                            scraped_candidate.id,
                            scraped_candidate
                        )
                    )
                candidacy = self.add_scraped_candidate_to_election(
                    scraped_candidate,
                    ocd_election
                )
                # check incumbent status
                if members_are_loaded:
                    if self.check_incumbent_status(candidacy):
                        candidacy.is_incumbent = True
                        candidacy.save()
                        if self.verbosity > 2:
                            self.log(' Identified as incumbent.')
                        # set is_incumbent False for all other candidacies
                        contest = candidacy.contest
                        contest.candidacies.exclude(
                            is_incumbent=True
                        ).update(is_incumbent=False)

    def add_scraped_candidate_to_election(self, scraped_candidate, ocd_election):
        """
        Converts scraped_candidate from the CAL-ACCESS site to an OCD Candidacy. Links it to an ocd_election.

        Returns a candidacy object.
        """
        # Get the candidate's form501 "statement of intention"
        form501 = self.get_form501_filing(scraped_candidate)

        #
        # Fallback system to connect the candidacy to a party
        #

        # Get the candidate's party, looking in our correction file for any fixes
        party = self.lookup_candidate_party_correction(
            scraped_candidate.name,
            ocd_election.date.year,
            scraped_candidate.election.parsed_name['type'],
            scraped_candidate.office_name,
        )

        # If the candidate is running for this office, it is by definition non-partisan
        if scraped_candidate.office_name == 'SUPERINTENDENT OF PUBLIC INSTRUCTION':
            party = Organization.objects.get(name="NO PARTY PREFERENCE")
        # If don't have their party yet, but they have a 501, let's use that
        elif form501 and not party:
            party = self.lookup_party(form501.party)
            # If the 501 doesn't have a party, try using the filer id
            if not party:
                party = self.get_party_for_filer_id(
                    int(form501.filer_id),
                    ocd_election.date,
                )
        # If they don't have a scraped_id, just try the filer_id
        elif scraped_candidate.scraped_id != '':
            party = self.get_party_for_filer_id(
                int(scraped_candidate.scraped_id),
                ocd_election.date,
            )
        # Otherwise, set the party to noneself.
        else:
            party = None

        #
        # Get or create the Contest
        #

        # if it's a primary election before 2012 for an office other than
        # superintendent of public instruction, include party in
        # get_or_create_contest criteria (if we have a party)
        if (
            'PRIMARY' in scraped_candidate.election.name and
            ocd_election.date.year < 2012 and
            scraped_candidate.office_name != 'SUPERINTENDENT OF PUBLIC INSTRUCTION'
        ):
            if not party:
                # use UNKNOWN party
                party = Organization.objects.get(identifiers__identifier=16011)

            contest, contest_created = self.get_or_create_contest(
                scraped_candidate,
                ocd_election,
                party=party,
            )
        else:
            contest, contest_created = self.get_or_create_contest(
                scraped_candidate,
                ocd_election,
            )

        if contest_created and self.verbosity > 2:
            self.log(' Created new CandidateContest: {}'.format(contest.name))

        #
        # Get or create Candidacy
        #

        # Set default registration_status
        registration_status = 'qualified'

        # Correct any names we now are bad
        name_fixes = {
            # http://www.sos.ca.gov/elections/prior-elections/statewide-election-results/primary-election-march-7-2000/certified-list-candidates/ # noqa
            'COURTRIGHT DONNA': 'COURTRIGHT, DONNA'
        }
        scraped_candidate_name = name_fixes.get(
            scraped_candidate.name,
            scraped_candidate.name
        )

        candidacy, candidacy_created = self.get_or_create_candidacy(
            contest,
            scraped_candidate_name,
            registration_status,
            filer_id=scraped_candidate.scraped_id,
        )

        if candidacy_created and self.verbosity > 2:
            template = ' Created new Candidacy: {0.candidate_name} in {0.post.label}'
            self.log(template.format(candidacy))

        #
        # Dress it up with extra
        #

        # add extra data from form501, if available
        if form501:
            self.link_form501_to_candidacy(form501.filing_id, candidacy)
            self.update_candidacy_from_form501s(candidacy)

            # if the scraped_candidate lacks a filer_id, add the
            # Form501Filing.filer_id
            if scraped_candidate.scraped_id == '':
                candidacy.person.identifiers.get_or_create(
                    scheme='calaccess_filer_id',
                    identifier=form501.filer_id,
                )
        # Fill the party if the candidacy doesn't have it
        if party and not candidacy.party:
            candidacy.party = party
            candidacy.save()

        # always update the source for the candidacy
        candidacy.sources.update_or_create(
            url=scraped_candidate.url,
            note='Last scraped on {dt:%Y-%m-%d}'.format(
                dt=scraped_candidate.last_modified,
            )
        )

        return candidacy

    def get_form501_filing(self, scraped_candidate):
        """
        Return a Form501Filing that matches the scraped Candidate.

        By default, return the latest Form501FilingVersion, unless earliest
        is set to True.

        If the scraped Candidate has a scraped_id, lookup the Form501Filing
        by filer_id. Otherwise, lookup using the candidate's name.

        Return None can't match to a single Form501Filing.
        """
        election_data = scraped_candidate.election.parsed_name
        office_data = self.parse_office_name(scraped_candidate.office_name)

        # filter all form501 lookups by office type, district and election year
        # get the most recently filed Form501 within the election_year
        q = Form501Filing.objects.filter(
            office__iexact=office_data['type'],
            district=office_data['district'],
            election_year__lte=election_data['year'],
        )

        if scraped_candidate.scraped_id != '':
            try:
                # first, try to get w/ filer_id and election_type
                form501 = q.filter(
                    filer_id=scraped_candidate.scraped_id,
                    election_type=election_data['type'],
                ).latest('date_filed')
            except Form501Filing.DoesNotExist:
                # if that fails, try dropping election_type from filter
                try:
                    form501 = q.filter(
                        filer_id=scraped_candidate.scraped_id,
                    ).latest('date_filed')
                except Form501Filing.DoesNotExist:
                    form501 = None
        else:
            # if no filer_id, combine name fields from form501
            # first try "<last_name>, <first_name>" format.
            q = q.annotate(
                full_name=Concat(
                    'last_name',
                    Value(', '),
                    'first_name',
                    output_field=CharField(),
                )
            )
            # check if there are any with the "<last_name>, <first_name>"
            if not q.filter(full_name=scraped_candidate.name).exists():
                # use "<last_name>, <first_name> <middle_name>" format
                q = q.annotate(
                    full_name=Concat(
                        'last_name',
                        Value(', '),
                        'first_name',
                        Value(' '),
                        'middle_name',
                        output_field=CharField(),
                    ),
                )

            try:
                # first, try to get w/ filer_id and election_type
                form501 = q.filter(
                    full_name=scraped_candidate.name,
                    election_type=election_data['type'],
                ).latest('date_filed')
            except Form501Filing.DoesNotExist:
                # if that fails, try dropping election_type from filter
                try:
                    form501 = q.filter(
                        full_name=scraped_candidate.name,
                    ).latest('date_filed')
                except Form501Filing.DoesNotExist:
                    form501 = None

        return form501

    def get_or_create_contest(self, scraped_candidate, ocd_election, party=None):
        """
        Get or create an OCD CandidateContest object using  and Election object.

        Returns a tuple (CandidateContest object, created), where created is a boolean
        specifying whether a CandidateContest was created.
        """
        office_name = scraped_candidate.office_name
        post, post_created = self.get_or_create_post(office_name)

        # Assume all "SPECIAL" candidate elections are for contests where the
        # previous term of the office was unexpired.
        if 'SPECIAL' in scraped_candidate.election.name:
            previous_term_unexpired = True
            scraped_election = scraped_candidate.election.name
            election_type = scraped_candidate.election.parsed_name['type']
            contest_name = '{0} ({1})'.format(office_name, election_type)
        else:
            previous_term_unexpired = False
            if party:
                if party.name == 'UNKNOWN':
                    contest_name = '{0} ({1} PARTY)'.format(office_name, party.name)
                else:
                    contest_name = '{0} ({1})'.format(office_name, party.name)
            else:
                contest_name = office_name

        contest, contest_created = CandidateContest.objects.get_or_create(
            election=ocd_election,
            name=contest_name,
            previous_term_unexpired=previous_term_unexpired,
            party=party,
            division=post.division,
        )

        # if contest was created, add the Post
        if contest_created:
            contest.posts.create(
                post=post,
            )

        # always update the source for the contest
        contest.sources.update_or_create(
            url=scraped_candidate.url,
            note='Last scraped on {dt:%Y-%m-%d}'.format(
                dt=scraped_candidate.last_modified,
            )
        )

        return (contest, contest_created)

    def check_incumbent_status(self, candidacy):
        """
        Check if the Candidacy is for the incumbent officeholder.

        Return True if:
        * Membership exists for the Person and Post linked to the Candidacy, and
        * Membership.end_date is NULL or has a year later than Election.date.year.
        """
        incumbent_q = Membership.objects.filter(
            post=candidacy.post,
            person=candidacy.person,
        ).annotate(
            # Cast end_date's value as an int, treat '' as NULL
            end_year=Cast(
                Case(When(end_date='', then=None)),
                IntegerField(),
            )
        ).filter(
            Q(end_year__gt=candidacy.election.date.year) |
            Q(end_date='')
        )
        if incumbent_q.exists():
            is_incumbent = True
        else:
            is_incumbent = False
        return is_incumbent

    def find_previous_undecided_contest(self, runoff_contest):
        """
        Find the undecided contest that preceeded runoff_contest.
        """
        # Get the contest's post (should only ever be one per contest)
        post = runoff_contest.posts.all()[0].post

        # Then try getting the most recent contest for the same post
        # that preceeds the runoff contest
        try:
            contest = CandidateContest.objects.filter(
                posts__post=post,
                election__date__lt=runoff_contest.election.date,
            ).latest('election__date')
        except CandidateContest.DoesNotExist:
            contest = None

        return contest
