# Copyright © 2024 Province of British Columbia
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
#     http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.

"""Tests for the Involuntary Dissolutions Job.
Test suite to ensure that the Involuntary Dissolutions Job is working as expected.
"""
from datetime import datetime, timedelta
from unittest.mock import MagicMock, patch

import pytest
import pytz
from datedelta import datedelta
from legal_api.models import Batch, BatchProcessing, Business, Configuration, db

from involuntary_dissolutions import initiate_dissolution_process, check_run_schedule, stage_2_process

from . import factory_batch, factory_batch_processing, factory_business


CREATED_DATE = (datetime.utcnow() + datedelta(days=-60)).replace(tzinfo=pytz.UTC)


def test_initiate_dissolution_process_job_already_ran(app, session):
    """Assert that the job is skipped correctly if it already ran today."""
    factory_business(identifier='BC1234567')

    # first run
    initiate_dissolution_process(app)
    batches = Batch.find_by(batch_type=Batch.BatchType.INVOLUNTARY_DISSOLUTION)
    assert len(batches) == 1

    # second run
    initiate_dissolution_process(app)
    batches = Batch.find_by(batch_type=Batch.BatchType.INVOLUNTARY_DISSOLUTION)
    assert not len(batches) > 1


def test_initiate_dissolution_process_zero_allowed(app, session):
    """Assert that the job is skipped correctly if no dissolutions are allowed."""
    factory_business(identifier='BC1234567')

    config = Configuration.find_by_name(config_name='NUM_DISSOLUTIONS_ALLOWED')
    config.val = '0'
    config.save()

    initiate_dissolution_process(app)
    batches = Batch.find_by(batch_type=Batch.BatchType.INVOLUNTARY_DISSOLUTION)
    assert len(batches) == 0


def test_initiate_dissolution_process(app, session):
    """Assert that batch and batch_processing entries are created correctly."""
    business_identifiers = ['BC0000001', 'BC0000002', 'BC0000003']
    for business_identifier in business_identifiers:
        factory_business(identifier=business_identifier)

    initiate_dissolution_process(app)

    batches = Batch.find_by(batch_type=Batch.BatchType.INVOLUNTARY_DISSOLUTION)
    assert len(batches) == 1
    batch = batches[0]
    assert batch.batch_type == Batch.BatchType.INVOLUNTARY_DISSOLUTION
    assert batch.status == Batch.BatchStatus.PROCESSING
    assert batch.size == 3
    assert batch.start_date.date() == datetime.now().date()

    batch_processings = BatchProcessing.find_by(batch_id=batch.id)
    assert len(batch_processings) == 3
    for i, batch_processing in enumerate(batch_processings):
        assert batch_processing.batch_id == batch.id
        assert batch_processing.business_identifier == business_identifiers[i]
        assert batch_processing.step == BatchProcessing.BatchProcessingStep.WARNING_LEVEL_1
        assert batch_processing.status == BatchProcessing.BatchProcessingStatus.PROCESSING
        assert batch_processing.created_date.date() == datetime.now().date()
        assert batch_processing.meta_data


def test_check_run_schedule():
    """Assert that schedule check validates the day of run based on cron string in config."""
    with patch.object(Configuration, 'find_by_name') as mock_find_by_name:
        mock_stage_1_config = MagicMock()
        mock_stage_2_config = MagicMock()
        mock_stage_3_config = MagicMock()
        mock_stage_1_config.val = '0 0 * * 1-2'
        mock_stage_2_config.val = '0 0 * * 2'
        mock_stage_3_config.val = '0 0 * * 3'
        mock_find_by_name.side_effect = [mock_stage_1_config, mock_stage_2_config, mock_stage_3_config]

        with patch('involuntary_dissolutions.datetime', wraps=datetime) as mock_datetime:
            mock_datetime.today.return_value = datetime(2024, 6, 4)
            cron_valid_1, cron_valid_2, cron_valid_3 = check_run_schedule()

            assert cron_valid_1 is True
            assert cron_valid_2 is True
            assert cron_valid_3 is False


@pytest.mark.parametrize(
    'test_name, batch_status, status, step, created_date, found', [
        (
            'FOUND',
            Batch.BatchStatus.PROCESSING,
            BatchProcessing.BatchProcessingStatus.PROCESSING,
            BatchProcessing.BatchProcessingStep.WARNING_LEVEL_1,
            CREATED_DATE,
            True
        ),
        (
            'NOT_FOUND_BATCH_STATUS',
            Batch.BatchStatus.HOLD,
            BatchProcessing.BatchProcessingStatus.PROCESSING,
            BatchProcessing.BatchProcessingStep.WARNING_LEVEL_1,
            CREATED_DATE,
            False
        ),
        (
            'NOT_FOUND_BATCH_PROCESSING_STATUS',
            Batch.BatchStatus.PROCESSING,
            BatchProcessing.BatchProcessingStatus.HOLD,
            BatchProcessing.BatchProcessingStep.WARNING_LEVEL_1,
            CREATED_DATE,
            False
        ),
        (
            'NOT_FOUND_STEP',
            Batch.BatchStatus.PROCESSING,
            BatchProcessing.BatchProcessingStatus.PROCESSING,
            BatchProcessing.BatchProcessingStep.WARNING_LEVEL_2,
            CREATED_DATE,
            False
        ),
        (
            'NOT_FOUND_CREATED_DATE',
            Batch.BatchStatus.PROCESSING,
            BatchProcessing.BatchProcessingStatus.PROCESSING,
            BatchProcessing.BatchProcessingStep.WARNING_LEVEL_1,
            datetime.utcnow(),
            False
        )
    ]

)
def test_stage_2_process_find_entry(app, session, test_name, batch_status, status, step, created_date, found):
    """Assert that only businesses that meet conditions can be processed for stage 2."""
    business = factory_business(identifier='BC1234567')

    batch = factory_batch(status=batch_status)
    last_modified = CREATED_DATE
    batch_processing = factory_batch_processing(
        batch_id=batch.id,
        business_id=business.id,
        identifier=business.identifier,
        status=status,
        step=step,
        created_date=created_date,
        last_modified=last_modified
    )

    stage_2_process(app)

    if found:
        assert batch_processing.last_modified != last_modified
    else:
        assert batch_processing.last_modified == last_modified


@pytest.mark.parametrize(
    'test_name, status, step', [
        (
            'MOVE_2_STAGE_2',
            BatchProcessing.BatchProcessingStatus.PROCESSING,
            BatchProcessing.BatchProcessingStep.WARNING_LEVEL_2
        ),
        (
            'MOVE_BACK_2_GOOD_STANDING',
            BatchProcessing.BatchProcessingStatus.WITHDRAWN,
            BatchProcessing.BatchProcessingStep.WARNING_LEVEL_1
        ),
    ]
)
def test_stage_2_process_update_business(app, session, test_name, status, step):
    """Assert that businesses are processed correctly."""
    business = factory_business(identifier='BC1234567')
    batch = factory_batch(status=Batch.BatchStatus.PROCESSING)
    batch_processing = factory_batch_processing(
        batch_id=batch.id,
        business_id=business.id,
        identifier=business.identifier,
        created_date=CREATED_DATE
    )

    if test_name == 'MOVE_BACK_2_GOOD_STANDING':
        business.last_ar_date = datetime.utcnow()
        business.save()

    stage_2_process(app)

    assert batch_processing.status == status
    assert batch_processing.step == step